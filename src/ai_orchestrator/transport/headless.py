"""Headless subprocess transport (ADR-002, ADR-010).

argv list with shell=False — no shell interpolation anywhere. Timeouts and
missing binaries become structured results, not exceptions: the engine's
fail-stop logic deals in TransportResults.

Process hygiene (ADR-034) and portability (ADR-035):

* Every child is started so that a timeout or a Ctrl-C kills the *whole
  tree* — provider CLIs spawn helpers (MCP servers, language servers, node
  workers) that a plain `proc.kill()` would orphan, still burning CPU and
  quota after baton has given up. POSIX: the child is its own session leader
  and `killpg` takes the group. Windows: the child gets its own process group
  and `taskkill /T` takes the tree.
* Because the child leaves the terminal's foreground group, it no longer
  receives the terminal's Ctrl-C by itself; the transport therefore forwards
  it explicitly (kill the tree, then re-raise).
* The executable is resolved with `shutil.which` before launch. On Windows
  the provider CLIs are npm shims (`claude.cmd`, `codex.cmd`) that
  `CreateProcess` cannot find from a bare name; on POSIX this is what `execvp`
  does anyway, so behaviour is unchanged there.
* Output is decoded as UTF-8 with `errors="replace"` — never the console's
  locale code page, which on Windows is not UTF-8 and would turn every
  non-ASCII character a provider prints into a decoding error or mojibake.
"""

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from ai_orchestrator.transport.base import Invocation, LineSink, TransportResult

IS_WINDOWS = sys.platform == "win32"

# How long to wait for a killed tree to actually exit before giving up on
# collecting its remaining output. Kill is unconditional, so this is generous.
_REAP_TIMEOUT_S = 5


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the child's whole process tree. Never raises: this runs on error paths."""
    if IS_WINDOWS:
        with contextlib.suppress(Exception):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=_REAP_TIMEOUT_S,
            )
    else:
        with contextlib.suppress(Exception):
            os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(Exception):
        proc.kill()


def resolve_executable(name: str) -> str:
    """The path `shutil.which` finds for `name`, or `name` itself when nothing is
    found (so the launch fails with the normal FileNotFoundError path)."""
    return shutil.which(name) or name


def _popen(invocation: Invocation) -> subprocess.Popen:
    env = {**os.environ, **invocation.env}
    argv = [resolve_executable(invocation.argv[0]), *invocation.argv[1:]]
    isolation = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if IS_WINDOWS
        else {"start_new_session": True}
    )
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=invocation.workdir,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        **isolation,
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
        except (FileNotFoundError, OSError) as exc:
            return _not_launched(invocation, exc, start)
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
            # running detached — see module docstring.
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
        except (FileNotFoundError, OSError) as exc:
            return _not_launched(invocation, exc, start)

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
            # Ctrl-C while streaming: the child would otherwise keep running
            # after baton exits (see module docstring).
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


def _not_launched(invocation: Invocation, exc: OSError, start: float) -> TransportResult:
    """The process never started: missing binary, or (Windows) a file that is not
    executable. Both are the same thing to the engine — a provider that is not
    there — and are reported in the same words so doctor/preflight stay readable."""
    if isinstance(exc, FileNotFoundError) or getattr(exc, "winerror", None) in (2, 193):
        error = f"binary not found: {invocation.argv[0]!r}"
    else:
        error = f"could not start {invocation.argv[0]!r}: {exc}"
    return TransportResult(
        exit_code=None, stdout="", stderr="", duration_s=time.monotonic() - start, error=error,
    )


def _reap(proc: subprocess.Popen) -> tuple[str, str]:
    """Collect whatever a killed child left in its pipes; never raises."""
    try:
        stdout, stderr = proc.communicate(timeout=_REAP_TIMEOUT_S)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return "", ""
    return stdout or "", stderr or ""
