"""Headless subprocess transport (ADR-002, ADR-010).

argv list with shell=False — no shell interpolation anywhere. Timeouts and
missing binaries become structured results, not exceptions: the engine's
fail-stop logic deals in TransportResults.

Process hygiene (ADR-034):

* Every child runs in **its own session** (`start_new_session=True`), so a
  timeout or a Ctrl-C kills the *whole tree* — provider CLIs spawn helpers
  (MCP servers, language servers, node workers) that a plain `proc.kill()`
  would orphan, still burning CPU and quota after baton has given up.
* Because a new session leaves the terminal's foreground process group, the
  child no longer receives the terminal's SIGINT by itself; the transport
  therefore forwards Ctrl-C explicitly (kill the tree, then re-raise).
* Output is decoded with `errors="replace"`: a single undecodable byte from a
  third-party process must degrade to U+FFFD in the log, never abort a stage.
"""

import contextlib
import os
import signal
import subprocess
import threading
import time

from ai_orchestrator.transport.base import Invocation, LineSink, TransportResult

# How long to wait for a killed tree to actually exit before giving up on
# collecting its remaining output. Kill is SIGKILL, so this is generous.
_REAP_TIMEOUT_S = 5


def _kill_tree(proc: subprocess.Popen) -> None:
    """SIGKILL the child's whole process group (it is its own session leader).

    Falls back to killing just the child where process groups are unavailable
    or the group is already gone. Never raises: this runs on error paths.
    """
    with contextlib.suppress(Exception):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(Exception):
        proc.kill()


def _popen(invocation: Invocation) -> subprocess.Popen:
    env = {**os.environ, **invocation.env}
    return subprocess.Popen(
        invocation.argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=invocation.workdir,
        env=env,
        text=True,
        errors="replace",
        shell=False,
        start_new_session=True,
    )


class HeadlessTransport:
    def run(
        self, invocation: Invocation, on_line: LineSink | None = None
    ) -> TransportResult:
        """Run the invocation; with `on_line`, stream stdout lines as they arrive.

        ADR-030: the streaming path exists so a long stage can show evidence of
        life. Without a sink the buffered path (`communicate`) is used — simpler,
        and the one `ask`/`review`/`doctor` take.
        """
        if on_line is not None:
            return self._run_streaming(invocation, on_line)
        start = time.monotonic()
        try:
            proc = _popen(invocation)
        except FileNotFoundError:
            return TransportResult(
                exit_code=None,
                stdout="",
                stderr="",
                duration_s=time.monotonic() - start,
                error=f"binary not found: {invocation.argv[0]!r}",
            )
        try:
            stdout, stderr = proc.communicate(invocation.stdin, timeout=invocation.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            stdout, stderr = _reap(proc)
            return TransportResult(
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
                duration_s=time.monotonic() - start,
                timed_out=True,
                error=f"timed out after {invocation.timeout_s}s",
            )
        except BaseException:
            # Ctrl-C (or anything else unexpected) must not leave the provider
            # running detached in its own session — see module docstring.
            _kill_tree(proc)
            _reap(proc)
            raise
        return TransportResult(
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_s=time.monotonic() - start,
        )

    def _run_streaming(self, invocation: Invocation, on_line: LineSink) -> TransportResult:
        """Popen + incremental stdout reads, with stdin and stderr on threads.

        stdin is written from a thread because a large prompt can fill the pipe
        buffer before the child starts reading, and stderr is drained from
        another so a chatty child cannot block on a full stderr pipe while we
        wait on stdout.
        """
        start = time.monotonic()
        try:
            proc = _popen(invocation)
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
            _kill_tree(proc)

        watchdog = threading.Timer(invocation.timeout_s, _kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()

        out_parts: list[str] = []
        try:
            with contextlib.suppress(OSError, ValueError):  # pipe closed under us
                for line in proc.stdout or ():
                    out_parts.append(line)
                    # A progress sink must never be able to fail a stage; the
                    # note is a convenience, the run is the product.
                    with contextlib.suppress(Exception):
                        on_line(line)
            proc.wait()
        except BaseException:
            # Ctrl-C while streaming: the child is in its own session and would
            # otherwise keep running after baton exits (see module docstring).
            watchdog.cancel()
            _kill_tree(proc)
            _reap(proc)
            raise
        finally:
            watchdog.cancel()
        draining.join(timeout=_REAP_TIMEOUT_S)

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


def _reap(proc: subprocess.Popen) -> tuple[str, str]:
    """Collect whatever a killed child left in its pipes; never raises."""
    try:
        stdout, stderr = proc.communicate(timeout=_REAP_TIMEOUT_S)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return "", ""
    return stdout or "", stderr or ""
