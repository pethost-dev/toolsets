"""What every asynchronous browser driver does with the sandbox's browser beside its members:
_sync_session's twin on Playwright's asyncio API, doing the same in the same order."""

from __future__ import annotations

from pethost.sandboxes import AsyncSandboxes
from playwright.async_api import Error, Locator, Page

from ._async_link import AsyncBrowserLink
from ._async_page import watch
from ._browser_shared import LINK_TTL_SECONDS, BrowserConnectionError, PageRefusal, plain_ref
from ._tabs import Tab, Tabs


class AsyncSession:
    """One sandbox's browser, as an asyncio driver holds it: see _sync_session.SyncSession."""

    def __init__(self) -> None:
        self.tabs: Tabs[Page] = Tabs()
        self.link = AsyncBrowserLink()
        self._sandboxes: AsyncSandboxes | None = None
        self._sandbox_id = ""
        self._link_ttl_seconds = LINK_TTL_SECONDS

    async def open(self, sandboxes: AsyncSandboxes, sandbox_id: str, link_ttl_seconds: int) -> None:
        """Connects to the sandbox's browser: see SyncSession.open."""
        self._sandboxes, self._sandbox_id, self._link_ttl_seconds = sandboxes, sandbox_id, link_ttl_seconds
        await self._connect(sandboxes)

    async def close(self) -> None:
        await self.link.close()

    @property
    def opened(self) -> bool:
        return self._sandboxes is not None

    async def ready(self) -> None:
        """The connection a member needs, made again when it dropped: see SyncSession.ready."""
        if self.link.connected():
            return
        if self._sandboxes is None:
            raise BrowserConnectionError("The driver was made without connect(): it has no sandbox's browser.")
        await self._connect(self._sandboxes)

    async def _connect(self, sandboxes: AsyncSandboxes) -> None:
        contexts = await self.link.open(sandboxes, self._sandbox_id, self._link_ttl_seconds)
        pages = [page for context in contexts for page in context.pages]
        for tab in self.tabs.connected([(page, await self.link.target_id(page)) for page in pages]):
            watch(tab.page, self.tabs)
        if self.tabs.active is None:
            self.watch(await self.link.new_page(), opened=False)
        for context in contexts:
            context.on("page", self._opened)

    def _opened(self, page: Page) -> None:
        self.watch(page, opened=True)

    def watch(self, page: Page, *, opened: bool) -> Tab[Page]:
        known = self.tabs.find(page)
        if known is not None:
            return known
        watch(page, self.tabs)
        return self.tabs.add(page, opened=opened)

    async def front(self, tab_id: str | None) -> Tab[Page]:
        """The tab a member acts on, shown on the desktop and made the active one."""
        tab = self.tabs.get(tab_id)
        await tab.page.bring_to_front()
        self.tabs.activate(tab)
        return tab

    async def element(self, tab: Tab[Page], ref: str) -> Locator:
        """The element of a ref, as Playwright resolves it in the page now."""
        locator = tab.page.get_by_ref(plain_ref(ref))
        try:
            found = await locator.count()
        except Error:  # a ref of an earlier document names a frame the page no longer has
            found = 0
        if found == 0:
            raise PageRefusal(f"No element has the ref {ref!r} on the page now: read the page again.")
        return locator

    async def new_tab(self) -> Tab[Page]:
        tab = self.watch(await self.link.new_page(), opened=True)
        return await self.front(tab.tab_id)

    async def close_tab(self, tab_id: str) -> None:
        tab = self.tabs.get(tab_id)
        if len(self.tabs.all) == 1:  # Chrome ends with its last tab: a blank one takes its place
            await self.new_tab()
        await tab.page.close()
        self.tabs.closed(tab.page)

    async def titles(self, tabs: list[Tab[Page]]) -> list[tuple[Tab[Page], str]]:
        """The tabs with their titles, as the browser reads them: see SyncSession.titles."""
        for tab in tabs:
            if not tab.target_id:
                self.tabs.identify(tab, await self.link.target_id(tab.page))
        titles = await self.link.titles()
        return [(tab, self.tabs.title(tab, titles)) for tab in tabs]
