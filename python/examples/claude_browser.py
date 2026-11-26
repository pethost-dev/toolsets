"""Claude browses in a sandbox's Chrome through the browser toolset: a new sandbox from our base, the
task from the command line, Claude's words printed as they come, the sandbox deleted at the end.

    pip install 'pethost-toolsets[claude,browser]'
    PETHOST_TOKEN=pth_... ANTHROPIC_API_KEY=sk-ant-... python examples/claude_browser.py "Open ..."
"""

from __future__ import annotations

import sys

from anthropic import Anthropic
from pethost.sandboxes import Sandboxes

from pethost_toolsets import ClaudeBrowser

TASK = "Open pethost.dev/sandboxes and tell me what a running sandbox of the smallest size costs an hour."


def main() -> None:
    task = " ".join(sys.argv[1:]) or TASK
    with Sandboxes() as sandboxes:  # The token: PETHOST_TOKEN.
        sandbox = sandboxes.create_sandbox("base")
        try:
            # The sandbox's egress allow-list (update_sandbox settings) bounds what the browser
            # reaches; a url_policy here would judge only the addresses Claude asks for.
            with ClaudeBrowser.connect(sandboxes, sandbox.sandbox_id) as browser:
                runner = Anthropic().beta.messages.tool_runner(
                    model="claude-opus-5-5",
                    max_tokens=16000,
                    tools=[browser],
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
