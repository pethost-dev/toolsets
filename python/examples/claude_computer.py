"""Claude works on a sandbox's desktop through the computer toolset: a new sandbox from our base, the
task from the command line, Claude's words printed as they come, the sandbox deleted at the end.

    PETHOST_TOKEN=pth_... ANTHROPIC_API_KEY=sk-ant-... python examples/claude_computer.py "Open Chrome and ..."
"""

from __future__ import annotations

import sys

from anthropic import Anthropic
from anthropic.tools.computer import BetaComputerConfirmContext
from pethost.sandboxes import Sandboxes

from pethost_toolsets import ClaudeComputer

TASK = "Open Chrome, find out what Pethost Agent Sandboxes are, and say it in one sentence."


def approve(context: BetaComputerConfirmContext) -> bool:
    # The SDK asks before every action. This desktop is a microVM made for this run, holding
    # nothing of yours, so every action runs; ask a person here where a desktop holds more.
    return True


def main() -> None:
    task = " ".join(sys.argv[1:]) or TASK
    with Sandboxes() as sandboxes:  # The token: PETHOST_TOKEN.
        sandbox = sandboxes.create_sandbox("base")
        try:
            with ClaudeComputer(sandboxes, sandbox.sandbox_id, confirm=approve) as computer:
                runner = Anthropic().beta.messages.tool_runner(
                    model="claude-opus-5-5",
                    max_tokens=16000,
                    tools=[computer],
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    messages=[{"role": "user", "content": task}],
                )
                for message in runner:
                    for block in message.content:
                        if block.type == "text":
                            print(block.text)
        finally:
            sandboxes.delete_sandbox(sandbox.sandbox_id)


if __name__ == "__main__":
    main()
