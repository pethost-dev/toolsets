"""What every browser driver shares beyond its tabs, Claude's and OpenAI's, synchronous and
asynchronous alike: the browser link as a credential and the server's words when it refuses one,
the refusals a model reads, Playwright's errors and a page's requests as a model reads them, and
the scripts they run in a page. Nothing here is of a model provider's SDK: each driver turns a
PageRefusal into its own provider's error."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:  # BrowserConnectionError is imported without Playwright (pethost_toolsets)
    from playwright.sync_api import ResourceTiming

LINK_TTL_SECONDS = 60
"""How long a browser link opens a connection: only the connection needs it, and it lasts past
the link, so the link is kept short, being the whole browser's credential."""

CONNECT_TIMEOUT_MS = 90_000
"""The browser link starts the desktop and its Chrome when they do not run, in up to 45 s."""

REFUSAL_TIMEOUT_MS = 10_000
"""How long the server may take to say why it refused a link."""

NAVIGATE_TIMEOUT_MS = 30_000
LOAD_WAIT_MS = 5_000
"""After a page's document is read, how long navigate waits for the rest of it to load."""

LOADED = "document.readyState === 'complete'"
"""A page's load, as the page itself tells it, which navigate waits for LOAD_WAIT_MS at most."""

PARSED = "document.readyState !== 'loading'"
"""A page's document parsed, as the page itself tells it: what a step in a tab's history waits for,
a page brought back from Chrome's back-forward cache firing no load events."""

ERROR_PAGE = re.compile(r"^chrome-error:")
ERROR_PAGE_MS = 2_000
"""How long Chrome's error page may take to show after a load failed."""

POLL_MS = 100
"""How often a wait asks the page: by time, not by animation frame, which Chrome does not run for
a window that does not show."""

PAGE_QUESTION_MS = 15_000
"""How long a page may take to answer a question of the driver's (where it is scrolled to, its
text): one busy in a script of its own answers none, and Playwright's evaluate waits with no end."""

PAGE_BUSY = f"The page did not answer within {PAGE_QUESTION_MS // 1000} s: a script of its own keeps it busy."

SCRIPT_MS = 30_000
"""How long a script may take to give its value when its member names no time: javascript_exec's."""

LOST = "The connection to the sandbox's browser was lost: the next call makes it again."

REF_TIMEOUT_MS = 5_000
"""How long an action on a ref waits for its element to be there and ready: a ref that a re-render
took away fails in this time rather than in Playwright's 30 s."""

SCROLL_SETTLE_MS = 300
"""How long scroll waits after the wheel: the page scrolls after the event, in an animation, and a
screenshot taken at once shows it where it was."""

DRAG_STEPS = 10
"""Pointer moves between a drag's ends, as a hand would make, for pages that track the move."""

VIEWPORT = """(() => {
  const v = window.visualViewport;
  return { x: v ? v.pageLeft : scrollX, y: v ? v.pageTop : scrollY, width: innerWidth, height: innerHeight };
})()"""
"""The viewport's size and where in the document it is scrolled to, in CSS pixels."""

PAGE_TEXT = """(() => {
  const articles = document.querySelectorAll('article');
  const root = articles.length === 1 ? articles[0] : (document.querySelector('main, [role=main]') || document.body);
  return root ? root.innerText : '';
})()"""
"""The page's visible text: its one article when it has one, else its main part, else its body."""

FIELD_KIND = "element => (element.tagName + ':' + (element.getAttribute('type') || '')).toLowerCase()"

URL_MAX = 300
"""Where a request's address is cut in read_network's lines: a data: URL can hold a whole file."""


class PageRefusal(Exception):
    """A member that cannot be done as asked, in words for the model: a ref the page no longer has,
    a key it does not know, a page busy in a script of its own. Each driver gives it to the model as
    its provider's error (Anthropic's ToolError, OpenAI's BrowserError)."""


class BrowserConnectionError(Exception):
    """connect() did not connect to the sandbox's browser, with the server's words when it refused
    the link (a stopped sandbox), and no token in them. A connection lost later is made again at the
    next call, whose failure the model reads as that call's error."""


def script_late(ms: int) -> str:
    return f"The script gave no answer within {ms / 1000:g} s."


class Secret:
    """A browser link's token, which every text the driver passes on goes through first: Playwright
    names the address it connects to in some of its errors."""

    def __init__(self, url: str) -> None:
        self._token = urlsplit(url).path.strip("/").split("/")[0]

    def scrub(self, text: str) -> str:
        return text.replace(self._token, "<token>") if self._token else text

    def __repr__(self) -> str:
        return "Secret(<hidden>)"


def refusal_url(url: str) -> str:
    """Where the server says why it refused a browser link: the link over http(s), at
    <link>/json/version, which it answers as it would the WebSocket's upgrade, whose failure
    Playwright reports by its status alone."""
    parts = urlsplit(url)
    scheme = {"wss": "https", "ws": "http"}.get(parts.scheme, parts.scheme)
    return urlunsplit((scheme, parts.netloc, parts.path.rstrip("/") + "/json/version", "", ""))


# REFUSAL_READ_MAX bounds what of a refusal is read: its first line is all the model is told, and a
# link to the sandbox reaches whatever the sandbox runs, which may answer without end.
REFUSAL_READ_MAX = 4096


def fetch_refusal(url: str, secret: Secret) -> str | None:
    """The server's own words for a link it refused, which it gives over http too (refusal_url),
    of which at most REFUSAL_READ_MAX bytes are read; none when it answers there, or not at all.
    Blocking: an async caller runs it in a thread."""
    try:
        with urllib.request.urlopen(refusal_url(url), timeout=REFUSAL_TIMEOUT_MS / 1000):
            return None
    except urllib.error.HTTPError as refused:
        body = refused.read(REFUSAL_READ_MAX).decode("utf-8", "replace")
        refused.close()
        return refusal_text(refused.code, body, secret)
    except (OSError, ValueError):
        return None


def refusal_text(status: int, body: str, secret: Secret) -> str | None:
    """The refusal as the model reads it: its status and the first line of the server's words; none
    when the server said nothing."""
    lines = body.strip().splitlines()
    return secret.scrub(f"{status} {lines[0]}") if lines else None


def error_text(error: Exception, secret: Secret) -> str:
    """A Playwright error as the model reads it: its first line, which says what failed (the lines
    after are Playwright's log of the call), with no token in it."""
    lines = str(error).strip().splitlines()
    return secret.scrub(lines[0] if lines else type(error).__name__)


class Answer(Protocol):
    """A request's response, as both of Playwright's APIs give it."""

    @property
    def status(self) -> int: ...

    @property
    def headers(self) -> dict[str, str]: ...


class Request(Protocol):
    """A page's request, as both of Playwright's APIs give it once it finished or failed."""

    @property
    def method(self) -> str: ...

    @property
    def url(self) -> str: ...

    @property
    def failure(self) -> str | None: ...

    @property
    def timing(self) -> ResourceTiming: ...

    @property
    def existing_response(self) -> Answer | None: ...


def request_line(request: Request) -> str:
    """A request as a network read tells it: its method, its address, then its status, content type
    and time, or why it failed. All of it is what Playwright's event brought: nothing is asked."""
    url = request.url if len(request.url) <= URL_MAX else request.url[:URL_MAX] + "…"
    if request.failure is not None:
        return f"{request.method} {url} failed: {request.failure}"

    response = request.existing_response
    status = str(response.status) if response is not None else "-"
    kind = response.headers.get("content-type", "") if response is not None else ""
    ms = request.timing["responseEnd"]
    took = f"{round(ms)} ms" if ms >= 0 else ""
    return " ".join(part for part in (request.method, url, status, kind, took) if part)


def plain_ref(ref: str) -> str:
    """A ref as Playwright resolves it ("e5"), from the forms a model may copy from read_page's text
    ("[ref=e5]", "ref=e5")."""
    return ref.strip("[]").removeprefix("ref=")
