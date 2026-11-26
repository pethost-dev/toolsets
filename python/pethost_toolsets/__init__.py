"""Drivers that put AI models' computer and browser tools on Pethost Agent Sandboxes, written by
hand on the generated SDK (pethost.sandboxes): each gives a model's tool calls to a sandbox's
desktop or its Chrome.

- ClaudeComputer, AsyncClaudeComputer: Claude's computer toolset (computer_toolset_20260801) on
  the sandbox's desktop, by ControlDesktop: `pethost-toolsets[claude]`.
- ClaudeBrowser, AsyncClaudeBrowser: Claude's browser toolset (browser_toolset_20260801) on the
  Chrome of the sandbox's desktop, by Playwright over its browser link:
  `pethost-toolsets[claude,browser]`.
- OpenAIComputer, AsyncOpenAIComputer: drivers of the openai SDK's ComputerToolset, on the
  desktop by ControlDesktop: `pethost-toolsets[openai]`.
- OpenAIBrowser, AsyncOpenAIBrowser: drivers of its BrowserToolset, on the desktop's Chrome by
  Playwright: `pethost-toolsets[openai,browser]`.
- OpenAICode, AsyncOpenAICode: computer use by code, exec_py and exec_js, run in the sandbox's
  code runtime: `pethost-toolsets[openai]`.

A name is imported when it is first used, so a driver whose extras are not installed costs nothing
until then.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._browser_shared import BrowserConnectionError as BrowserConnectionError
    from ._desktop import DesktopRefusedError as DesktopRefusedError
    from .claude_async_browser import AsyncClaudeBrowser as AsyncClaudeBrowser
    from .claude_browser import ClaudeBrowser as ClaudeBrowser
    from .claude_computer import AsyncClaudeComputer as AsyncClaudeComputer, ClaudeComputer as ClaudeComputer
    from .openai_async_browser import AsyncOpenAIBrowser as AsyncOpenAIBrowser
    from .openai_browser import OpenAIBrowser as OpenAIBrowser
    from .openai_code import AsyncOpenAICode as AsyncOpenAICode, OpenAICode as OpenAICode
    from .openai_computer import AsyncOpenAIComputer as AsyncOpenAIComputer, OpenAIComputer as OpenAIComputer

__all__ = [
    "ClaudeComputer",
    "AsyncClaudeComputer",
    "ClaudeBrowser",
    "AsyncClaudeBrowser",
    "OpenAIComputer",
    "AsyncOpenAIComputer",
    "OpenAIBrowser",
    "AsyncOpenAIBrowser",
    "OpenAICode",
    "AsyncOpenAICode",
    "BrowserConnectionError",
    "DesktopRefusedError",
]

MODULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "ClaudeComputer": ("claude_computer", ("claude",)),
    "AsyncClaudeComputer": ("claude_computer", ("claude",)),
    "ClaudeBrowser": ("claude_browser", ("claude", "browser")),
    "AsyncClaudeBrowser": ("claude_async_browser", ("claude", "browser")),
    "OpenAIComputer": ("openai_computer", ("openai",)),
    "AsyncOpenAIComputer": ("openai_computer", ("openai",)),
    "OpenAIBrowser": ("openai_browser", ("openai", "browser")),
    "AsyncOpenAIBrowser": ("openai_async_browser", ("openai", "browser")),
    "OpenAICode": ("openai_code", ("openai",)),
    "AsyncOpenAICode": ("openai_code", ("openai",)),
    "BrowserConnectionError": ("_browser_shared", ()),
    "DesktopRefusedError": ("_desktop", ()),
}
"""Each name's module, and the extras that module needs."""

PACKAGES = {"anthropic": "claude", "openai": "openai", "playwright": "browser"}
"""The extra each optional package comes with."""


def __getattr__(name: str) -> object:
    if name not in MODULES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module, extras = MODULES[name]
    try:
        return getattr(importlib.import_module(f".{module}", __name__), name)
    except ModuleNotFoundError as error:
        package = (error.name or "").split(".")[0]
        if PACKAGES.get(package) not in extras:
            raise
        needs = f"pethost-toolsets[{','.join(extras)}]"
        raise ModuleNotFoundError(f"{name} needs {needs}: pip install '{needs}'") from error
