"""OpenAI's computer use by code on a sandbox, as OpenAI's guide recommends for GPT-6 Astra: the
model writes Python, which drives the desktop with PyAutoGUI, and JavaScript, which drives its
Chrome with Playwright, and the sandbox's code runtime runs each in a session that keeps its
variables. A new sandbox from our base, the task from the command line, the model's last answer
printed, the sandbox deleted at the end.

    pip install 'pethost-toolsets[openai]'
    PETHOST_TOKEN=pth_... OPENAI_API_KEY=sk-... python examples/openai_code.py "Find ..."
"""

from __future__ import annotations

import sys

from openai import OpenAI
from openai.lib.responses_tool_runner import ResponsesToolRunner
from pethost.sandboxes import Sandboxes

from pethost_toolsets import OpenAICode

TASK = "Open pethost.dev in the browser and tell me what the page's heading says."


def main() -> None:
    task = " ".join(sys.argv[1:]) or TASK
    with Sandboxes() as sandboxes:  # The token: PETHOST_TOKEN.
        sandbox = sandboxes.create_sandbox("base")
        try:
            with OpenAICode(sandboxes, sandbox.sandbox_id) as code:
                runner = ResponsesToolRunner(functions=code.functions)
                response = runner.run(
                    OpenAI(),
                    {
                        "model": "gpt-6-astra",
                        "instructions": "You use a Linux desktop with Chrome on it, by writing code with your tools.",
                        "input": task,
                    },
                    max_steps=50,
                )
                print(response.output_text)
        finally:
            sandboxes.delete_sandbox(sandbox.sandbox_id)


if __name__ == "__main__":
    main()
