"""What Claude's two browser drivers (claude_browser, claude_async_browser) share and OpenAI's do not:
the members they leave off, what every click member takes, and the tabs and what changed among
them in the browser toolset's own words."""

from __future__ import annotations

from typing import Protocol

from anthropic.tools.browser import BetaDialogDismissed
from anthropic.types.beta import (
    BetaBrowserClickTarget,
    BetaBrowserStateChangeTabOpenedParam,
    BetaBrowserStateTabEntryParam,
    BetaBrowserToolsetConfigsParam,
)

from ._tabs import Change, PageT, Tab

StateChange = BetaBrowserStateChangeTabOpenedParam | BetaDialogDismissed


class ClickInput(Protocol):
    """What every click member takes."""

    @property
    def target(self) -> BetaBrowserClickTarget: ...

    @property
    def modifiers(self) -> str | None: ...

    @property
    def tab_id(self) -> str | None: ...


def served_configs(configs: BetaBrowserToolsetConfigsParam | None) -> BetaBrowserToolsetConfigsParam:
    """The caller's configs, with the members the drivers leave off turned off, since a driver that
    overrides execute serves every member as far as the SDK knows: find matches a description in
    words, which takes a model; file_upload would read files where the browser is not."""
    return {**(configs or {}), "find": {"enabled": False}, "file_upload": {"enabled": False}}


def state_changes(changes: list[Change]) -> list[StateChange]:
    return [state_change(change) for change in changes]


def state_change(change: Change) -> StateChange:
    if change.kind == "tab_opened":
        return {"type": "tab_opened", "tab_id": change.tab_id}
    return BetaDialogDismissed(kind=change.dialog, message=change.message)


def tab_entry(tab: Tab[PageT], title: str, url: str, active: Tab[PageT] | None) -> BetaBrowserStateTabEntryParam:
    """The tab as the browser state lists it."""
    return {"tab_id": tab.tab_id, "title": title, "url": url, "active": tab is active}
