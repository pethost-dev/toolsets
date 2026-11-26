"""What OpenAI's two browser drivers (openai_browser, openai_async_browser) share and Claude's do not:
the refusals the model reads, as the SDK's BrowserError, the tabs as its state, and its inputs as
Playwright's arguments (keys, a scroll's distance, the points of the viewport)."""

from __future__ import annotations

import base64
import re
from urllib.parse import urlsplit
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from typing import Protocol

from openai.lib.browser import BrowserError, BrowserReadV1, BrowserState, BrowserTab
from openai.types.responses.response_input_image_content_param import ResponseInputImageContentParam
from pethost.sandboxes import SandboxesError
from playwright.sync_api import Error  # the asyncio API's Error is the same class

from . import _browser_input as given
from ._aria import bounded
from ._browser_shared import LOST, BrowserConnectionError, PageRefusal, Secret, error_text
from ._tabs import Change, PageT, Tab

SCROLL_PAGE = 0.8
"""What of the viewport a scroll of no amount takes, as PageDown scrolls: the lines it ends on are
still in view. The TypeScript driver takes the same."""

DIALOG_TEXT_MAX = 300
"""The most of a dismissed dialog's text an action's result quotes: a page writes what it likes
there."""


class Link(Protocol):
    """The connection, synchronous or asynchronous, as far as a refusal needs it."""

    @property
    def secret(self) -> Secret: ...

    def connected(self) -> bool: ...


@contextmanager
def refusals(link: Link) -> Generator[None]:
    """A member's failure as the SDK's BrowserError, whose words reach the model; any other error
    would reach it as "Browser action failed.", saying nothing. No token is in them."""
    try:
        yield
    except PageRefusal as refusal:
        raise BrowserError(str(refusal)) from None
    except (BrowserConnectionError, SandboxesError) as error:
        raise BrowserError(link.secret.scrub(str(error))) from None
    except Error as error:
        raise BrowserError(error_text(error, link.secret) if link.connected() else LOST) from None


def state(tabs: Sequence[tuple[Tab[PageT], str, str]], active: Tab[PageT] | None) -> BrowserState:
    """The tabs, each with its title and address, as the SDK's state: one active when any is open,
    the active one or else the last. The SDK cuts each address to its origin before the model sees
    it. No observation is reported: with one, a tab at an address other than http, https or
    about:blank (chrome://newtab/, data:) fails the whole state, and the run with it."""
    if active is None or all(tab is not active for tab, _, _ in tabs):
        active = tabs[-1][0] if tabs else None
    entries: list[BrowserTab] = [
        {"id": tab.tab_id, "title": title, "url": state_url(url), "active": tab is active} for tab, title, url in tabs
    ]
    return {"tabs": entries}


def state_url(url: str) -> str:
    """A tab's address as the SDK can read it, which it then cuts to its origin or its scheme: one it
    could not parse (no scheme, an http address with no host) is about:blank, rather than a state
    that fails and ends the run."""
    try:
        parts = urlsplit(url)
        hostless = parts.scheme in ("http", "https") and not parts.hostname
    except ValueError:
        return "about:blank"
    return "about:blank" if not parts.scheme or hostless else url


def notes(changes: list[Change], opened_here: str = "") -> str | None:
    """What happened beside an action, as its result: a tab the page opened, a dialog dismissed. The
    SDK's state has no word for them without an observation (state). A tab the action opened itself
    (new_tab, opened_here) is the state's active one, and no news."""
    lines = [note(change) for change in changes if not (change.kind == "tab_opened" and change.tab_id == opened_here)]
    return "\n".join(lines) if lines else None


def note(change: Change) -> str:
    if change.kind == "tab_opened":
        return f"The page opened tab {change.tab_id}."
    where = f" in {change.tab_id}" if change.tab_id else ""
    text = change.message if len(change.message) <= DIALOG_TEXT_MAX else change.message[:DIALOG_TEXT_MAX] + "…"
    return f"A {change.dialog} dialog{where} was dismissed: {text!r}"


def image(png: bytes | str) -> ResponseInputImageContentParam:
    """A PNG, or its base64, as the model's input image, at its own resolution: the viewport's CSS
    pixels, the coordinates click_at takes."""
    data = png if isinstance(png, str) else base64.b64encode(png).decode("ascii")
    return {"type": "input_image", "image_url": f"data:image/png;base64,{data}", "detail": "original"}


def keys(names: Sequence[str]) -> list[str]:
    """A key combination, each key as Playwright names it, from the names a model writes: "Control",
    "ctrl", "Enter", "Return", or a chord in one name, "ctrl+a". With other keys a letter is the key,
    not its capital: ["Control", "A"] is ctrl+a, where Playwright would press shift+a for a lone "A"."""
    pressed = [key for name in names for key in given.chord_keys(name)]
    if not pressed:
        raise PageRefusal("keys: name at least one key")
    if len(pressed) > 1:
        pressed = [key.lower() if len(key) == 1 and key.isascii() and key.isalpha() else key for key in pressed]
    return pressed


def scroll(direction: str, amount: int, width: float, height: float) -> tuple[float, float]:
    """A scroll as the wheel's deltas, right and down positive: `amount` CSS pixels, or most of the
    viewport when it is 0, as PageDown scrolls."""
    across = direction in ("left", "right")
    pixels = float(amount) if amount > 0 else SCROLL_PAGE * (width if across else height)
    sign = -1.0 if direction in ("up", "left") else 1.0
    return (sign * pixels, 0.0) if across else (0.0, sign * pixels)


def inside(points: Sequence[tuple[int, int]], width: float, height: float) -> None:
    """Refuses a point out of the viewport, which the browser would take as nowhere."""
    for x, y in points:
        if x >= width or y >= height:
            raise PageRefusal(
                f"({x}, {y}) is out of the viewport, {width:g}×{height:g}: take a screenshot for the coordinates."
            )


def region(region: Sequence[int], width: float, height: float) -> None:
    """Refuses a zoom that reaches out of the viewport."""
    left, top, right, bottom = region
    if right > width or bottom > height:
        raise PageRefusal(f"region: [{left}, {top}, {right}, {bottom}] reaches out of the viewport, {width:g}×{height:g}")


def diagnostics(lines: list[str], limit: int, source: str) -> BrowserReadV1:
    """The last `limit` lines a tab's console or its requests wrote since the last read, as a read
    with no elements. A request's query string is left out: it may hold a token."""
    taken = lines[-limit:]
    if source == "network":
        taken = [QUERY.sub("?…", line) for line in taken]
    text = "\n".join(taken) if taken else "Nothing since the last read."
    return {"version": 1, "text": unicode(bounded(text, "read it more often")), "elements": [], "omitted": []}


QUERY = re.compile(r"\?\S*")


def unicode(text: str) -> str:
    """The text with a lone surrogate (a JavaScript string can hold one) replaced: the SDK refuses a
    result that is not valid Unicode, and the run with it."""
    return text.encode("utf-8", "replace").decode("utf-8")


def wait_text(text: str) -> str:
    """wait_for's text as the SDK checked it: its whitespace folded."""
    return " ".join(text.split())
