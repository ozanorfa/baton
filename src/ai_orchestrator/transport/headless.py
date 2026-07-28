"""Headless subprocess transport (ADR-002, ADR-010).

argv list with shell=False — no shell interpolation anywhere. Timeouts and
missing binaries become structured results, not exceptions: the engine's
fail-stop logic deals in TransportResults.
"""

import contextlib
import os
import subprocess
import threading
import time

from ai_orchestrator.transport.base import Invocation, LineSink, TransportResult


class HeadlessTransport:
    def run(
        self, invocation: Invocation, on_line: LineSink | None = None
    ) -> TransportResult:
        """Run the invocation; with `on_line`, stream stdout lines as they arrive.

        ADR-030: the streaming path exists so a long stage can show evidence of
        life. It is deliberately opt-in — without a sink this is the original
        single `subprocess.run` call, byte for byte, because the buffered path
        is load-bearing and well understood.
        """
        if on_line is not None:
            return self._run_streaming(invocation, on_line)
        env = {**os.environ, **invocation.env}
        start = time.monotonic()
        try:
            completed = subprocess.run(
                invocation.argv,
                input=invocation.stdin,
                cwd=invocation.workdir,
                env=env,
                capture_output=True,
                text=True,
                timeout=invocation.timeout_s,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            return TransportResult(
                exit_code=None,
                stdout=_decode(exc.stdout),
                stderr=_decode(exc.stderr),
                duration_s=time.monotonic() - start,
                timed_out=True,
                error=f"timed out after {invocation.timeout_s}s",
            )
        except FileNotFoundError:
            return TransportResult(
                exit_code=None,
                stdout="",
                stderr="",
                duration_s=time.monotonic() - start,
                error=f"binary not found: {invocation.argv[0]!r}",
            )
        return TransportResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_s=time.monotonic() - start,
        )



    def _run_streaming(self, invocation: Invocation, on_line: LineSink) -> TransportResult:
        """Popen + incremental stdout reads, with stdin and stderr on threads.

        stdin is written from a thread because a large prompt can fill the pipe
        buffer before the child starts reading, and stderr is drained from
        another so a chatty child cannot block on a full stderr pipe while we
        wait on stdout.
        """
        env = {**os.environ, **invocation.env}
        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                invocation.argv,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=invocation.workdir, env=env, text=True, shell=False,
            )
        except FileNotFoundError:
            return TransportResult(
                exit_code=None, stdout="", stderr="",
                duration_s=time.monotonic() - start,
                error=f"binary not found: {invocation.argv[0]!r}",
            )

        def _feed() -> None:
            try:
                if proc.stdin is not None:
                    proc.stdin.write(invocation.stdin)
                    proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        stderr_parts: list[str] = []

        def _drain_stderr() -> None:
            try:
                if proc.stderr is not None:
                    stderr_parts.append(proc.stderr.read())
            except (OSError, ValueError):
                pass

        writer = threading.Thread(target=_feed, daemon=True)
        draining = threading.Thread(target=_drain_stderr, daemon=True)
        writer.start()
        draining.start()

        # A watchdog, not a deadline checked between lines: reading stdout blocks,
        # so a provider that hangs while silent would never be cut off — which
        # would lose a timeout the buffered path has always enforced (T34).
        # Caught by test_streaming_times_out_and_reports_it.
        expired = threading.Event()

        def _kill_on_timeout() -> None:
            expired.set()
            with contextlib.suppress(Exception):
                proc.kill()

        watchdog = threading.Timer(invocation.timeout_s, _kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()

        out_parts: list[str] = []
        try:
            for line in proc.stdout or ():
                out_parts.append(line)
                # A progress sink must never be able to fail a stage; the note
                # is a convenience, the run is the product.
                with contextlib.suppress(Exception):
                    on_line(line)
        except (OSError, ValueError):
            pass

        proc.wait()
        watchdog.cancel()
        draining.join(timeout=2)

        if expired.is_set():
            return TransportResult(
                exit_code=None, stdout="".join(out_parts), stderr="".join(stderr_parts),
                duration_s=time.monotonic() - start, timed_out=True,
                error=f"timed out after {invocation.timeout_s}s",
            )
        return TransportResult(
            exit_code=proc.returncode,
            stdout="".join(out_parts),
            stderr="".join(stderr_parts),
            duration_s=time.monotonic() - start,
        )


def _decode(data: str | bytes | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode(errors="replace")
    return data
