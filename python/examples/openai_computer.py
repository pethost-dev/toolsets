"""OpenAI's computer use on a sandbox's desktop through the openai SDK's ComputerToolset: a new
sandbox from our base, the task from the command line, the model's last answer printed, the
sandbox deleted at the end. Each action the model sends is one ControlDesktop call, and it sees
a screenshot of the whole screen after each batch.

    pip install 'pethost-toolsets[openai]'
    PETHOST_TOKEN=pth_... OPENAI_API_KEY=sk-... python examples/openai_computer.py "Open Chrome and ..."
"""

from __future__ import annotations

import sys

from openai import ComputerToolset, OpenAI
from pethost.sandboxes import Sandboxes

from pethost_toolsets import OpenAIComputer

TASK = "Open Chrome, find out what Pethost Agent Sandboxes are, and say it in one sentence."


def main() -> None:
    task = " ".join(sys.argv[1:]) or TASK
    with Sandboxes() as sandboxes:  # The token: PETHOST_TOKEN.
        sandbox = sandboxes.create_sandbox("base")
        try:
            toolset = ComputerToolset(OpenAIComputer(sandboxes, sandbox.sandbox_id))
            response = toolset.run(
                OpenAI(),
                {
                    "model": "gpt-6.2-sol",
                    "instructions": "You use a Linux desktop with Chrome on it to do what you are asked.",
                    "input": task,
                },
                max_steps=50,
            )
            print(response.output_text)
        finally:
            sandboxes.delete_sandbox(sandbox.sandbox_id)


if __name__ == "__main__":
    main()
