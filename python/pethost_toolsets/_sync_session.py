"""What every synchronous browser driver does with the sandbox's browser beside its members, Claude's
and OpenAI's alike: the connection through a browser link, made again through a new link when it
dropped, the tabs with the ids they keep across connections (_tabs), the tab a member acts on, the
element of a ref, and each tab's title as the browser reads it. _async_session is its asyncio twin,
and does the same in the same order."""

from __future__ import annotations

from pethost.sandboxes import Sandboxes
from playwright.sync_api import Error, Locator, Page

from ._browser_shared import LINK_TTL_SECONDS, BrowserConnectionError, PageRefusal, plain_ref
from ._sync_link import SyncBrowserLink
from ._sync_page import watch
from ._tabs import Tab, Tabs


class SyncSession:
    """One sandbox's browser, as a driver holds it: open() connects it, close() disconnects and
    leaves the browser running in the sandbox."""

    def __init__(self) -> None:
        self.tabs: Tabs[Page] = Tabs()
        self.link = SyncBrowserLink()
        self._sandboxes: Sandboxes | None = None
        self._sandbox_id = ""
        self._link_ttl_seconds = LINK_TTL_SECONDS

    def open(self, sandboxes: Sandboxes, sandbox_id: str, link_ttl_seconds: int) -> None:
        """Connects to the sandbox's browser, starting its desktop when it does not run (some seconds),
        and keeps what it takes to connect again. A link the server refuses raises
        BrowserConnectionError with the server's words."""
        self._sandboxes, self._sandbox_id, self._link_ttl_seconds = sandboxes, sandbox_id, link_ttl_seconds
        self._connect(sandboxes)

    def close(self) -> None:
        self.link.close()

    @property
    def opened(self) -> bool:
        """Whether open() was called: a driver made otherwise has nothing to connect to."""
        return self._sandboxes is not None

    def ready(self) -> None:
        """The connection a member needs, made again when it dropped. One that cannot be made raises
        BrowserConnectionError or the SDK's SandboxesError, which the driver gives the model as the
        member's error: the next call tries again."""
        if self.link.connected():
            return
        if self._sandboxes is None:
            raise BrowserConnectionError("The driver was made without connect(): it has no sandbox's browser.")
        self._connect(self._sandboxes)

    def _connect(self, sandboxes: Sandboxes) -> None:
        """A connection through a new link, its tabs with the ids they had, and every page that appears
        on it from now on reported as opened."""
        contexts = self.link.open(sandboxes, self._sandbox_id, self._link_ttl_seconds)
        pages = [page for context in contexts for page in context.pages]
        for tab in self.tabs.connected([(page, self.link.target_id(page)) for page in pages]):
            watch(tab.page, self.tabs)
        if self.tabs.active is None:
            self.watch(self.link.new_page(), opened=False)
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

    def front(self, tab_id: str | None) -> Tab[Page]:
        """The tab a member acts on, shown on the desktop (a hidden one draws nothing to capture)
        and made the active one."""
        tab = self.tabs.get(tab_id)
        tab.page.bring_to_front()
        self.tabs.activate(tab)
        return tab

    def element(self, tab: Tab[Page], ref: str) -> Locator:
        """The element of a ref, as Playwright resolves it in the page now."""
        locator = tab.page.get_by_ref(plain_ref(ref))
        try:
            found = locator.count()
        except Error:  # a ref of an earlier document names a frame the page no longer has
            found = 0
        if found == 0:
            raise PageRefusal(f"No element has the ref {ref!r} on the page now: read the page again.")
        return locator

    def new_tab(self) -> Tab[Page]:
        """A new blank tab, reported as opened, and made the active one."""
        tab = self.watch(self.link.new_page(), opened=True)
        return self.front(tab.tab_id)

    def close_tab(self, tab_id: str) -> None:
        tab = self.tabs.get(tab_id)
        if len(self.tabs.all) == 1:  # Chrome ends with its last tab: a blank one takes its place
            self.new_tab()
        tab.page.close()
        self.tabs.closed(tab.page)

    def titles(self, tabs: list[Tab[Page]]) -> list[tuple[Tab[Page], str]]:
        """The tabs with their titles, as the browser reads them: page.title() asks the page, which
        may be busy."""
        for tab in tabs:
            if not tab.target_id:
                self.tabs.identify(tab, self.link.target_id(tab.page))
        titles = self.link.titles()
        return [(tab, self.tabs.title(tab, titles)) for tab in tabs]
