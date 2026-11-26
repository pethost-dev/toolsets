"""The asynchronous browser driver's connection to a sandbox's Chrome: _sync_link's twin on
Playwright's asyncio API, doing the same in the same order."""

from __future__ import annotations

import asyncio

from typing import Any, Protocol

from pethost.sandboxes import AsyncSandboxes, BrowserLink
from playwright.async_api import Browser, BrowserContext, Error, Page, Playwright, async_playwright

from ._browser_shared import (
    CONNECT_TIMEOUT_MS,
    BrowserConnectionError,
    Secret,
    error_text,
    fetch_refusal,
)


class CDP(Protocol):
    """A Chrome DevTools Protocol session, as the driver calls it."""

    async def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def detach(self) -> None: ...


class AsyncBrowserLink:
    """Playwright, connected to one sandbox's browser by open() and disconnected by close(), which
    leaves the browser running in the sandbox."""

    def __init__(self) -> None:
        self.secret = Secret("")
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._cdp: CDP | None = None

    async def open(self, sandboxes: AsyncSandboxes, sandbox_id: str, link_ttl_seconds: int) -> list[BrowserContext]:
        """Connects through a new link, letting go of a connection that dropped, and gives the
        browser's contexts: its own profile's first."""
        await self._disconnect()
        link = await sandboxes.create_link(sandbox_id, browser=BrowserLink(), ttl_seconds=link_ttl_seconds)
        self.secret = Secret(link.url)
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        failure = ""
        # no_defaults: the desktop's Chrome keeps its own settings, which a person on the desktop
        # and every other client share: a download goes to ~/Downloads rather than to Playwright's
        # temporary folder, gone at the disconnect, and no focus or media is emulated.
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                link.url, timeout=CONNECT_TIMEOUT_MS, no_defaults=True
            )
        except Error as error:
            failure = await refusal(link.url, self.secret) or error_text(error, self.secret)
        if self._browser is None:
            raise BrowserConnectionError(f"Playwright did not connect to the sandbox's browser: {failure}")

        self._cdp = await self._browser.new_browser_cdp_session()
        return self._browser.contexts

    async def close(self) -> None:
        await self._disconnect()
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    def connected(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def new_page(self) -> Page:
        assert self._browser is not None, "a page is opened on a connection that open() made"
        return await self._browser.contexts[0].new_page()

    async def target_id(self, page: Page) -> str:
        """The page's id in the protocol, by which titles() names it; empty for a page closed
        meanwhile, which its close event takes out."""
        try:
            session = await page_session(page)
            try:
                return str((await session.send("Target.getTargetInfo"))["targetInfo"]["targetId"])
            finally:
                await session.detach()
        except Error:
            return ""

    async def titles(self) -> dict[str, str]:
        """The titles of the browser's pages by their target ids, read from the browser rather than
        from the pages, any of which may be busy; none when the browser does not answer."""
        if self._cdp is None:
            return {}
        try:
            targets = (await self._cdp.send("Target.getTargets"))["targetInfos"]
        except Error:
            return {}
        return {str(target["targetId"]): str(target.get("title", "")) for target in targets}

    async def capture(self, page: Page, clip: dict[str, float]) -> str:
        """A PNG of a part of the page, in base64, drawn at the clip's scale: Playwright's own
        screenshot draws a part only at its size."""
        session = await page_session(page)
        try:
            return str((await session.send("Page.captureScreenshot", {"format": "png", "clip": clip}))["data"])
        finally:
            await session.detach()

    async def _disconnect(self) -> None:
        browser, self._browser, self._cdp = self._browser, None, None
        if browser is None:
            return
        try:
            await browser.close()  # a browser connected over CDP is disconnected, not closed
        except Error:
            pass  # its connection is gone already


async def page_session(page: Page) -> CDP:
    return await page.context.new_cdp_session(page)


async def refusal(url: str, secret: Secret) -> str | None:
    """The server's own words for a link it refused: see _sync_link.refusal."""
    return await asyncio.to_thread(fetch_refusal, url, secret)
