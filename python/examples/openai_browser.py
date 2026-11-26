"""OpenAI's model browses in a sandbox's Chrome through the openai SDK's BrowserToolset: a new sandbox
from our base, the task from the command line, the model's last answer printed, the sandbox deleted
at the end. The model reads pages by Playwright's snapshot and acts on its refs.

    pip install 'pethost-toolsets[openai,browser]'
    PETHOST_TOKEN=pth_... OPENAI_API_KEY=sk-... python examples/openai_browser.py "Open ..."
"""

from __future__ import annotations

import sys
from urllib.parse import urlsplit

from openai import OpenAI
from openai.lib.browser import BrowserConfirmContext, BrowserToolset
from openai.lib.responses_tool_runner import ResponsesToolRunner
from pethost.sandboxes import Sandboxes

from pethost_toolsets import OpenAIBrowser

TASK = "Open pethost.dev/sandboxes and tell me what a running sandbox of the smallest size costs an hour."


def confirm(context: BrowserConfirmContext) -> bool:
    """Every action is allowed: the sandbox is this run's alone and is deleted at the end. A browser
    signed in to something of yours would ask a person here."""
    return True


def url_policy(context: BrowserConfirmContext, url: str) -> bool:
    """Web addresses only. The sandbox's egress allow-list (update_sandbox settings) bounds what the
    browser reaches, redirects and a page's own requests included, which this does not see."""
    return urlsplit(url).scheme in ("http", "https")


def main() -> None:
    task = " ".join(sys.argv[1:]) or TASK
    with Sandboxes() as sandboxes:  # The token: PETHOST_TOKEN.
        sandbox = sandboxes.create_sandbox("base")
        try:
            with OpenAIBrowser.connect(sandboxes, sandbox.sandbox_id) as driver:
                tools = BrowserToolset(driver, confirm=confirm, url_policy=url_policy)
                response = ResponsesToolRunner(browser=tools).run(
                    OpenAI(),
                    {"model": "gpt-6.2-astra", "store": False, "input": task},
                    max_steps=30,
                )
                print(response.output_text)
        finally:
            sandboxes.delete_sandbox(sandbox.sandbox_id)


if __name__ == "__main__":
    main()
