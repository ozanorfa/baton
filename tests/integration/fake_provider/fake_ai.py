#!/usr/bin/env python3
"""Fake AI CLI for integration tests (T18/T29).

Speaks the transport contract exactly like a real provider binary: prompt on
stdin, result on stdout, exit code semantics. Behavior is driven by
directives embedded in the prompt so tests stay declarative:

    [[fail:message]]        exit 1 with `message` on stderr
    [[sleep:N]]             sleep N seconds before answering (timeout tests)
    [[output:text]]         reply with exactly `text`
    [[write:path:content]]  create a file in the cwd (edit-stage simulation)

Any directive may be scoped to one pipeline stage with `@role`, matched
against the prompt's `# Role: <name>` heading (from the role templates):

    [[fail@coder:boom]]     only the coder stage fails; others act normally

Zero tokens, zero network, fully deterministic.
"""

import re
import sys
import time

DIRECTIVE = re.compile(r"\[\[(\w+)(?:@(\w+))?:([^\]]*)\]\]")


def main() -> int:
    if "--version" in sys.argv:
        print("fake-ai 1.0")
        return 0

    prompt = sys.stdin.read()
    role_match = re.search(r"# Role: (\w+)", prompt)
    role = role_match.group(1).lower() if role_match else None

    directives = [
        (kind, arg)
        for kind, scope, arg in DIRECTIVE.findall(prompt)
        if scope is None or scope == "" or scope.lower() == role
    ]

    for kind, arg in directives:
        if kind == "sleep":
            time.sleep(int(arg))

    for kind, arg in directives:
        if kind == "fail":
            sys.stderr.write(arg or "scripted failure")
            return 1

    for kind, arg in directives:
        if kind == "write":
            path, _, content = arg.partition(":")
            with open(path, "w") as f:
                f.write(content + "\n")

    for kind, arg in directives:
        if kind == "output":
            print(arg)
            return 0

    first_line = prompt.strip().splitlines()[0] if prompt.strip() else "(empty)"
    print(f"FAKE RESPONSE to: {first_line[:60]} ({len(prompt)} prompt chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
