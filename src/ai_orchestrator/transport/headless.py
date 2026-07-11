"""Headless subprocess transport (ADR-002, ADR-010).

argv list with shell=False — no shell interpolation anywhere. Timeouts and
missing binaries become structured results, not exceptions: the engine's
fail-stop logic deals in TransportResults.
"""

import os
import subprocess
import time

from ai_orchestrator.transport.base import Invocation, TransportResult


class HeadlessTransport:
    def run(self, invocation: Invocation) -> TransportResult:
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


def _decode(data: str | bytes | None) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode(errors="replace")
    return data
