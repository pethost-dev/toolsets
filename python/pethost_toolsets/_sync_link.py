"""The synchronous browser driver's connection to a sandbox's Chrome: Playwright over a browser link,
made again through a new link when it dropped, and the few Chrome DevTools Protocol calls
Playwright has no method for. _async_link is its asyncio twin, and does the same in the same order."""

from __future__ import annotations

from typing import Any, Protocol

from pethost.sandboxes import BrowserLink, Sandboxes
from playwright.sync_api import Browser, BrowserContext, Error, Page, Playwright, sync_playwright

from ._browser_shared import (
    CONNECT_TIMEOUT_MS,
    BrowserConnectionError,
    Secret,
    error_text,
    fetch_refusal,
)


class CDP(Protocol):
    """A Chrome DevTools Protocol session, as the driver calls it."""

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def detach(self) -> None: ...


class SyncBrowserLink:
    """Playwright, connected to one sandbox's browser by open() and disconnected by close(), which
    leaves the browser running in the sandbox."""

    def __init__(self) -> None:
        self.secret = Secret("")
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._cdp: CDP | None = None

    def open(self, sandboxes: Sandboxes, sandbox_id: str, link_ttl_seconds: int) -> list[BrowserContext]:
        """Connects through a new link, letting go of a connection that dropped, and gives the
        browser's contexts: its own profile's first."""
        self._disconnect()
        link = sandboxes.create_link(sandbox_id, browser=BrowserLink(), ttl_seconds=link_ttl_seconds)
        self.secret = Secret(link.url)
        if self._playwright is None:
            self._playwright = sync_playwright().start()

        failure = ""
        # no_defaults: the desktop's Chrome keeps its own settings, which a person on the desktop
        # and every other client share: a download goes to ~/Downloads rather than to Playwright's
        # temporary folder, gone at the disconnect, and no focus or media is emulated.
        try:
            self._browser = self._playwright.chromium.connect_over_cdp(
                link.url, timeout=CONNECT_TIMEOUT_MS, no_defaults=True
            )
        except Error as error:
            failure = refusal(link.url, self.secret) or error_text(error, self.secret)
        if self._browser is None:
            raise BrowserConnectionError(f"Playwright did not connect to the sandbox's browser: {failure}")

        self._cdp = self._browser.new_browser_cdp_session()
        return self._browser.contexts

    def close(self) -> None:
        self._disconnect()
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    def new_page(self) -> Page:
        assert self._browser is not None, "a page is opened on a connection that open() made"
        return self._browser.contexts[0].new_page()

    def target_id(self, page: Page) -> str:
        """The page's id in the protocol, by which titles() names it; empty for a page closed
        meanwhile, which its close event takes out."""
        try:
            session = page_session(page)
            try:
                return str(session.send("Target.getTargetInfo")["targetInfo"]["targetId"])
            finally:
                session.detach()
        except Error:
            return ""

    def titles(self) -> dict[str, str]:
        """The titles of the browser's pages by their target ids, read from the browser rather than
        from the pages, any of which may be busy; none when the browser does not answer."""
        if self._cdp is None:
            return {}
        try:
            targets = self._cdp.send("Target.getTargets")["targetInfos"]
        except Error:
            return {}
        return {str(target["targetId"]): str(target.get("title", "")) for target in targets}

    def capture(self, page: Page, clip: dict[str, float]) -> str:
        """A PNG of a part of the page, in base64, drawn at the clip's scale: Playwright's own
        screenshot draws a part only at its size."""
        session = page_session(page)
        try:
            return str(session.send("Page.captureScreenshot", {"format": "png", "clip": clip})["data"])
        finally:
            session.detach()

    def _disconnect(self) -> None:
        browser, self._browser, self._cdp = self._browser, None, None
        if browser is None:
            return
        try:
            browser.close()  # a browser connected over CDP is disconnected, not closed
        except Error:
            pass  # its connection is gone already


def page_session(page: Page) -> CDP:
    return page.context.new_cdp_session(page)


def refusal(url: str, secret: Secret) -> str | None:
    """The server's own words for a link it refused ("sandbox … is stopped: resume it …"), which it
    gives over http too (refusal_url); none when it answers there, or not at all."""
    return fetch_refusal(url, secret)
