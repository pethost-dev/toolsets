"""What the synchronous browser driver does with a page beyond one of Playwright's own calls: it
watches the page's events into its tab, holds keys and lets each go whatever failed, asks the
page questions and runs a script within a time, and navigates. _async_page is its asyncio twin,
and does the same in the same order but for a script, which asyncio can give up waiting for."""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from typing import Any

from playwright.sync_api import Dialog, Error, Keyboard, Page, Response, TimeoutError

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

SCRIPT = """([script, ms]) => {
  let value = globalThis.eval(script);
  if (typeof value === 'function') value = value();
  if (!value || typeof value.then !== 'function') return { value };
  let timer;
  const late = new Promise((resolve) => { timer = setTimeout(() => resolve(null), ms); });
  return Promise.race([Promise.resolve(value).then((value) => ({ value })), late]).finally(() => clearTimeout(timer));
}"""
"""A page script of a member (javascript_exec, run_script), run as Playwright's evaluate runs one
(its value, called when it is a function, awaited when it is a promise), with a promise waited for
`ms` at most: its value as {value}, or null when it was late."""


def watch(page: Page, tabs: Tabs[Page]) -> None:
    """The page's events into its tab: its closing, its dialogs (dismissed, as no member answers
    one), its console lines and uncaught errors, and its requests once they finished or failed."""
    page.on("close", tabs.closed)
    page.on("dialog", lambda dialog: dismiss(page, dialog, tabs))
    page.on("console", lambda message: tabs.console_line(page, f"[{message.type}] {message.text}"))
    page.on("pageerror", lambda error: tabs.console_line(page, f"[uncaught] {error.message}"))
    page.on("requestfinished", lambda request: tabs.network_line(page, request_line(request)))
    page.on("requestfailed", lambda request: tabs.network_line(page, request_line(request)))


def dismiss(page: Page, dialog: Dialog, tabs: Tabs[Page]) -> None:
    tabs.dialog_dismissed(page, dialog.type, dialog.message)
    try:
        dialog.dismiss()
    except Error:
        pass  # another client of the browser answered it first


@contextmanager
def holding(keyboard: Keyboard, keys: Sequence[str]) -> Generator[None, None, None]:
    """The keys pressed down in order, then let go in reverse: each one that went down, whatever
    failed. Playwright's own press leaves the keys before a name it does not know held
    ("ctrl+minus"), and every later click and key of the tab would carry them."""
    down: list[str] = []
    try:
        for key in keys:
            keyboard.down(key)
            down.append(key)
        yield
    finally:
        for key in reversed(down):
            keyboard.up(key)


def press(keyboard: Keyboard, keys: Sequence[str]) -> None:
    """A chord pressed and let go (holding)."""
    with holding(keyboard, keys):
        pass


def ask(page: Page, expression: str) -> Any:
    """The value of a question to the page (VIEWPORT, PAGE_TEXT), or PageRefusal once PAGE_QUESTION_MS
    passed: Playwright keeps the time of a wait for a function's value outside the page, where an
    evaluate has none. The value comes inside an object, which the wait takes as given at once."""
    try:
        handle = page.wait_for_function(f"() => ({{ value: {expression} }})", polling=POLL_MS, timeout=PAGE_QUESTION_MS)
    except TimeoutError:
        raise PageRefusal(PAGE_BUSY) from None
    try:
        return handle.json_value()["value"]
    finally:
        handle.dispose()


def run_script(page: Page, script: str, ms: int = SCRIPT_MS) -> Any:
    """The value of a page script, or PageRefusal when a promise it gave has not settled within ms.

    ponytail: a script that keeps the page's own thread busy (a loop with no end) is waited for with
    no end, as Playwright's synchronous API cannot give up a call: the asyncio drivers give up on it
    too (README.md); bounding it here takes a page question that Playwright retries, which would run
    the script again after a navigation."""
    answer = page.evaluate(SCRIPT, [script, ms])
    if answer is None:
        raise PageRefusal(script_late(ms))
    return answer["value"]


def go(page: Page, url: str) -> Response | None:
    """The tab to an address, or back, forward or reload in its history, once the new document is
    parsed and then loaded, LOAD_WAIT_MS at most: a page still loading its images is there to act
    on. Chrome shows its error page a moment after Playwright reports a load that failed, and that
    navigation would cut the tab's next one short: it is waited for before the failure goes on."""
    try:
        response = step(page, url)
    except TimeoutError:
        raise
    except Error:
        try:
            page.wait_for_url(ERROR_PAGE, wait_until="commit", timeout=ERROR_PAGE_MS)
        except Error:
            pass  # a failure with no error page, as a download's
        raise

    try:
        page.wait_for_function(LOADED, polling=POLL_MS, timeout=LOAD_WAIT_MS).dispose()
    except Error:
        pass
    return response


def step(page: Page, url: str) -> Response | None:
    word = url.strip().lower()
    if word == "back":
        return page.go_back(timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
    if word == "forward":
        return page.go_forward(timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
    if word == "reload":
        return page.reload(timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
    return page.goto(given.address(url), timeout=NAVIGATE_TIMEOUT_MS, wait_until="domcontentloaded")
