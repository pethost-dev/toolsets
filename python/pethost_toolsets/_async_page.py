"""What the asynchronous browser driver does with a page beyond one of Playwright's own calls:
_sync_page's twin on Playwright's asyncio API, doing the same in the same order, but for a script,
which asyncio gives up waiting for whatever keeps it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from playwright.async_api import Dialog, Error, Keyboard, Page, Response, TimeoutError

from . import _browser_input as given
from ._browser_shared import (
    ERROR_PAGE,
    ERROR_PAGE_MS,
    LOAD_WAIT_MS,
    LOADED,
    NAVIGATE_TIMEOUT_MS,
    PAGE_BUSY,
    PAGE_QUESTION_MS,
    POLL_MS,
    SCRIPT_MS,
    PageRefusal,
    request_line,
    script_late,
)
from ._tabs import Tabs


def watch(page: Page, tabs: Tabs[Page]) -> None:
    """The page's events into its tab: see _sync_page.watch."""
    page.on("close", tabs.closed)
    page.on("dialog", lambda dialog: dismiss(page, dialog, tabs))
    page.on("console", lambda message: tabs.console_line(page, f"[{message.type}] {message.text}"))
    page.on("pageerror", lambda error: tabs.console_line(page, f"[uncaught] {error.message}"))
    page.on("requestfinished", lambda request: tabs.network_line(page, request_line(request)))
    page.on("requestfailed", lambda request: tabs.network_line(page, request_line(request)))


async def dismiss(page: Page, dialog: Dialog, tabs: Tabs[Page]) -> None:
    tabs.dialog_dismissed(page, dialog.type, dialog.message)
    try:
        await dialog.dismiss()
    except Error:
        pass  # another client of the browser answered it first


@asynccontextmanager
async def holding(keyboard: Keyboard, keys: Sequence[str]) -> AsyncGenerator[None, None]:
    """The keys pressed down in order, then let go in reverse: see _sync_page.holding."""
    down: list[str] = []
    try:
        for key in keys:
            await keyboard.down(key)
            down.append(key)
        yield
    finally:
        for key in reversed(down):
            await keyboard.up(key)


async def press(keyboard: Keyboard, keys: Sequence[str]) -> None:
    """A chord pressed and let go (holding)."""
    async with holding(keyboard, keys):
        pass


async def ask(page: Page, expression: str) -> Any:
    """The value of a question to the page, or PageRefusal once PAGE_QUESTION_MS passed: see
    _sync_page.ask."""
    try:
        handle = await page.wait_for_function(
            f"() => ({{ value: {expression} }})", polling=POLL_MS, timeout=PAGE_QUESTION_MS
        )
    except TimeoutError:
        raise PageRefusal(PAGE_BUSY) from None
    try:
        return (await handle.json_value())["value"]
    finally:
        await handle.dispose()


async def run_script(page: Page, script: str, ms: int = SCRIPT_MS) -> Any:
    """The value of a page script, as Playwright's evaluate gives it, or PageRefusal when it has none
    within ms, a promise that does not settle or a loop with no end alike: the evaluate goes on in
    the page unwatched."""
    try:
        return await asyncio.wait_for(page.evaluate(script), ms / 1000)
    except asyncio.TimeoutError:
        raise PageRefusal(script_late(ms)) from None


async def go(page: Page, url: str) -> Response | None:
    """The tab to an address, or a step in its history: see _sync_page.go."""
    try:
        response = await step(page, url)
    except TimeoutError:
        raise
    except Error:
        try:
            await page.wait_for_url(ERROR_PAGE, wait_until="commit", timeout=ERROR_PAGE_MS)
        except Error:
            pass  # a failure with no error page, as a download's
        raise

    try:
        await (await page.wait_for_function(LOADED, polling=POLL_MS, timeout=LOAD_WAIT_MS)).dispose()
    except Error:
        pass
    return response


async def step(page: Page, url: str) -> Response | None:
    word = url.strip().lower()
    if word == "back":
        return await page.go_back(timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
    if word == "forward":
        return await page.go_forward(timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
    if word == "reload":
        return await page.reload(timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
    return await page.goto(given.address(url), timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
