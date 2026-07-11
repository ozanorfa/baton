#!/usr/bin/env python3
"""Fake AI CLI for integration tests (T18).

Speaks the transport contract exactly like a real provider binary: prompt on
stdin, result on stdout, exit code semantics. Behavior is driven by
directives embedded in the prompt so tests stay declarative:

    [[fail:message]]   exit 1 with `message` on stderr
    [[sleep:N]]        sleep N seconds before answering (timeout tests)
    [[output:text]]    reply with exactly `text`

Zero tokens, zero network, fully deterministic.
"""

import re
import sys
import time


def main() -> int:
    if "--version" in sys.argv:
        print("fake-ai 1.0")
        return 0

    prompt = sys.stdin.read()

    sleep = re.search(r"\[\[sleep:(\d+)\]\]", prompt)
    if sleep:
        time.sleep(int(sleep.group(1)))

    fail = re.search(r"\[\[fail:([^\]]*)\]\]", prompt)
    if fail:
        sys.stderr.write(fail.group(1) or "scripted failure")
        return 1

    output = re.search(r"\[\[output:([^\]]*)\]\]", prompt)
    if output:
        print(output.group(1))
        return 0

    first_line = prompt.strip().splitlines()[0] if prompt.strip() else "(empty)"
    print(f"FAKE RESPONSE to: {first_line[:60]} ({len(prompt)} prompt chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
