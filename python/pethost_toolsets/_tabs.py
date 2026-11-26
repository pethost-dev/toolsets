"""The browser's tabs as a browser driver knows them: an id for each page the driver has seen, the
active one (where a member without tab_id acts), what changed since the driver last asked (a tab
opened, a dialog dismissed), and what each page wrote to its console and requested since the last
read. Each driver says it in its provider's words.

A tab's id outlives the connection it was given in: it is kept by Chrome's own id of the tab (its
target), so that after a connection dropped, the next one gives each tab the id it had.

It holds Playwright's pages without calling them, so the synchronous drivers and the asynchronous
ones share it: each feeds it the browser's events and asks it which page a call is for."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

from ._aria import bounded
from ._browser_shared import PageRefusal

PageT = TypeVar("PageT")

LOG_MAX = 1000
"""The lines a tab keeps of its console and of its requests, for the members that read them: the
latest."""


@dataclass(frozen=True)
class Change:
    """Something that happened in the browser beside a member's own effect: a tab opened (by the
    page, or by new_tab), or a dialog the driver dismissed, as no member answers one."""

    kind: Literal["tab_opened", "dialog_dismissed"]
    tab_id: str = ""
    dialog: str = ""
    """A dismissed dialog's type, as Playwright names it: alert, beforeunload, confirm, prompt."""
    message: str = ""


@dataclass(eq=False)
class Tab(Generic[PageT]):
    tab_id: str
    page: PageT
    target_id: str = ""
    """The Chrome DevTools Protocol's id of its page, by which its title is read."""
    console: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_MAX))
    network: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_MAX))


class Tabs(Generic[PageT]):
    def __init__(self) -> None:
        self._tabs: list[Tab[PageT]] = []
        self._ids: dict[str, str] = {}
        """Each tab id given, by its target: what a later connection gives the same tab again."""
        self._numbered = 0
        self._changes: list[Change] = []
        self._active: Tab[PageT] | None = None
        self._chosen = ""
        """The tab id a member last acted on, which a later connection makes the active tab again.
        A page's close event leaves it, since a connection that drops closes every page."""

    @property
    def all(self) -> list[Tab[PageT]]:
        return list(self._tabs)

    @property
    def active(self) -> Tab[PageT] | None:
        return self._active

    def connected(self, pages: Sequence[tuple[PageT, str]]) -> list[Tab[PageT]]:
        """The tabs of a connection just made, from its pages and their targets: a tab has the id an
        earlier connection gave it, else a new one, and the active tab is the one a member last
        acted on, else the last."""
        self._tabs = []
        self._active = None
        tabs = [self.add(page, target_id, opened=False) for page, target_id in pages]
        chosen = next((tab for tab in tabs if tab.tab_id == self._chosen), None)
        self._active = chosen or (tabs[-1] if tabs else None)
        return tabs

    def add(self, page: PageT, target_id: str = "", *, opened: bool) -> Tab[PageT]:
        """A page the driver has not seen: a tab of the browser at the start, or one opened since,
        which the next report tells as opened."""
        known = self.find(page)
        if known is not None:
            return known

        tab_id = self._ids.get(target_id) if target_id else None
        if tab_id is None:
            self._numbered += 1
            tab_id = f"tab_{self._numbered}"
        tab = Tab(tab_id, page)
        self.identify(tab, target_id)
        self._tabs.append(tab)
        if self._active is None:
            self._active = tab
        if opened:
            self._changes.append(Change("tab_opened", tab_id=tab.tab_id))
        return tab

    def identify(self, tab: Tab[PageT], target_id: str) -> None:
        """The tab's target, once known: none for a page closed before it was asked."""
        tab.target_id = target_id
        if target_id:
            self._ids[target_id] = tab.tab_id

    def activate(self, tab: Tab[PageT]) -> None:
        """The tab a member acted on, where the members without tab_id act from now on."""
        self._active = tab
        self._chosen = tab.tab_id

    def find(self, page: PageT) -> Tab[PageT] | None:
        return next((tab for tab in self._tabs if tab.page is page), None)

    def get(self, tab_id: str | None) -> Tab[PageT]:
        """The tab a member names, or the active one when it names none."""
        if tab_id is None:
            if self._active is None:
                raise PageRefusal("No tab is open: open one with new_tab.")
            return self._active

        tab = next((tab for tab in self._tabs if tab.tab_id == tab_id), None)
        if tab is None:
            raise PageRefusal(f"No tab is {tab_id!r}: the browser state lists the open ones.")
        return tab

    def closed(self, page: PageT) -> None:
        tab = self.find(page)
        if tab is None:
            return
        self._tabs.remove(tab)
        if self._active is tab:
            self._active = self._tabs[-1] if self._tabs else None

    def dialog_dismissed(self, page: PageT, kind: str, message: str) -> None:
        tab = self.find(page)
        tab_id = tab.tab_id if tab is not None else ""
        self._changes.append(Change("dialog_dismissed", tab_id=tab_id, dialog=kind, message=message))

    def console_line(self, page: PageT, line: str) -> None:
        tab = self.find(page)
        if tab is not None:
            tab.console.append(line)

    def network_line(self, page: PageT, line: str) -> None:
        tab = self.find(page)
        if tab is not None:
            tab.network.append(line)

    def title(self, tab: Tab[PageT], titles: Mapping[str, str]) -> str:
        """The tab's title, from the browser's titles by target id (Target.getTargets)."""
        return titles.get(tab.target_id, "")

    def drain(self) -> list[Change]:
        changes, self._changes = self._changes, []
        return changes


def taken(lines: deque[str]) -> str:
    """A tab's lines of one kind since the last read, which the read takes away."""
    text = "\n".join(lines)
    lines.clear()
    return bounded(text, "read it more often") if text else "Nothing since the last read."
