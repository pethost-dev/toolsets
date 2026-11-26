"""Claude's browser toolset (browser_toolset_20260801) on the Chrome of a sandbox's desktop, through
Playwright over the sandbox's browser link: ClaudeBrowser, for Anthropic. AsyncClaudeBrowser, for
AsyncAnthropic, is in claude_async_browser and does the same in the same order.

The link is a credential for the whole browser and every site it is signed in to: it goes to
Playwright alone, and no text the driver makes holds its token (_browser_shared.Secret). A
connection that drops is made again through a new link at the next call, and the tabs keep their
ids (_sync_session, _tabs). The refs are Playwright's, from its snapshot of the page, which
resolves them in the page as it is at each action; the reading of a page's text follows
Anthropic's example driver (claude-quickstarts, browser-toolset)."""

from __future__ import annotations

import base64
import json

from typing import Self

from anthropic import NOT_GIVEN, NotGiven
from anthropic.tools import ToolError, ToolsetUsageError
from anthropic.tools.browser import (
    BetaAbstractBrowserToolset20260801,
    BetaBrowserMemberResult,
    BetaBrowserNavigateResult,
    BetaBrowserState,
    BetaConfirmCallable,
    BetaScreenshotResult,
    BetaToolConfigs,
    BetaToolsetCallContext,
    BetaURLPolicy,
)
from anthropic.types import beta
from anthropic.types.beta import BetaBrowserRefTarget, BetaBrowserStateTabEntryParam
from pethost.sandboxes import Sandboxes, SandboxesError
from playwright.sync_api import Error, Locator, Page

from . import _aria as aria
from . import _browser_input as given
from ._browser_shared import (
    DRAG_STEPS,
    FIELD_KIND,
    LINK_TTL_SECONDS,
    LOST,
    PAGE_TEXT,
    REF_TIMEOUT_MS,
    SCROLL_SETTLE_MS,
    VIEWPORT,
    BrowserConnectionError,
    PageRefusal,
    error_text,
    plain_ref,
)
from ._claude_browser import ClickInput, served_configs, state_changes, tab_entry
from ._sync_page import ask, go, holding, press, run_script
from ._sync_session import SyncSession
from ._tabs import Tab, taken


class ClaudeBrowser(BetaAbstractBrowserToolset20260801):
    """The browser toolset on one sandbox's Chrome. Make it with ClaudeBrowser.connect(sandboxes,
    sandbox_id); close() disconnects and leaves the browser running in the sandbox. Use it from
    the thread that made it, as Playwright's synchronous API asks."""

    def __init__(
        self,
        *,
        configs: beta.BetaBrowserToolsetConfigsParam | None = None,
        confirm: BetaConfirmCallable | None = None,
        url_policy: BetaURLPolicy | NotGiven = NOT_GIVEN,
        tool_configs: BetaToolConfigs | None = None,
    ) -> None:
        """The SDK's options (find and file_upload stay off). connect() takes the same."""
        super().__init__(
            configs=served_configs(configs), confirm=confirm, url_policy=url_policy, tool_configs=tool_configs
        )
        self._session = SyncSession()
        self._tabs = self._session.tabs
        self._link = self._session.link

    @classmethod
    def connect(
        cls,
        sandboxes: Sandboxes,
        sandbox_id: str,
        *,
        link_ttl_seconds: int = LINK_TTL_SECONDS,
        configs: beta.BetaBrowserToolsetConfigsParam | None = None,
        confirm: BetaConfirmCallable | None = None,
        url_policy: BetaURLPolicy | NotGiven = NOT_GIVEN,
        tool_configs: BetaToolConfigs | None = None,
    ) -> Self:
        """Connects to the sandbox's browser, starting its desktop when it does not run (some seconds).
        `link_ttl_seconds` is how long each link may open its connection, which then lasts until
        close(). A link the server refuses (a stopped sandbox) raises BrowserConnectionError with the
        server's words."""
        toolset = cls(configs=configs, confirm=confirm, url_policy=url_policy, tool_configs=tool_configs)
        try:
            toolset._session.open(sandboxes, sandbox_id, link_ttl_seconds)
        except BaseException:
            toolset.close()
            raise
        return toolset

    def close(self) -> None:
        super().close()
        self._session.close()

    def _ready(self) -> None:
        """The connection a member needs, made again when it dropped: one that cannot be made is the
        member's error, and the next call tries again. A driver made without connect() has none to
        make, which Claude cannot act on: the run stops."""
        if not self._session.opened:
            raise ToolsetUsageError("Make the browser toolset with connect().")
        try:
            self._session.ready()
        except (SandboxesError, BrowserConnectionError) as error:
            raise ToolError(str(error)) from None

    def execute(
        self, context: BetaToolsetCallContext, name: beta.BetaBrowserMemberName, input: beta.BetaBrowserMemberInput
    ) -> BetaBrowserMemberResult:
        failure = ""
        try:
            self._ready()
            return super().execute(context, name, input)
        except PageRefusal as refusal:
            failure = str(refusal)
        except Error as error:
            failure = error_text(error, self._link.secret) if self._link.connected() else LOST
        raise ToolError(failure)

    def _browser_state(self, context: BetaToolsetCallContext) -> BetaBrowserState:
        """The tabs after a call; none while the connection is lost, rather than an error that would
        end the run."""
        changes = state_changes(self._tabs.drain())
        if not self._link.connected():
            return BetaBrowserState(tabs=[], state_changes=[*changes])
        return BetaBrowserState(tabs=self._entries(self._tabs.all), state_changes=[*changes])

    def _front(self, tab_id: str | None) -> Tab[Page]:
        return self._session.front(tab_id)

    def _element(self, tab: Tab[Page], ref: str) -> Locator:
        return self._session.element(tab, ref)

    def _entries(self, tabs: list[Tab[Page]]) -> list[BetaBrowserStateTabEntryParam]:
        """The tabs as the browser state lists them, their titles as the browser reads them."""
        return [tab_entry(tab, title, tab.page.url, self._tabs.active) for tab, title in self._session.titles(tabs)]

    def navigate(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserNavigateInput
    ) -> BetaBrowserNavigateResult:
        tab = self._front(input.tab_id)
        response = go(tab.page, input.url)
        status = response.status if response is not None else None
        entry = self._entries([tab])[0]
        return BetaBrowserNavigateResult(url=entry["url"], status=status, title=entry["title"] or None)

    def screenshot(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserScreenshotInput
    ) -> BetaScreenshotResult:
        image = self._front(input.tab_id).page.screenshot(type="png", scale="css")
        return BetaScreenshotResult(data=base64.b64encode(image).decode("ascii"))

    def zoom(self, context: BetaToolsetCallContext, input: beta.BetaBrowserZoomInput) -> BetaScreenshotResult:
        page = self._front(input.tab_id).page
        view = ask(page, VIEWPORT)
        clip = given.zoom_clip(input.region, view["x"], view["y"], view["width"], view["height"])
        return BetaScreenshotResult(data=self._link.capture(page, clip))

    def _click(self, input: ClickInput, button: given.Button, count: int) -> None:
        tab = self._front(input.tab_id)
        held = given.modifiers(input.modifiers)
        target = input.target
        if isinstance(target, BetaBrowserRefTarget):
            locator = self._element(tab, target.ref)
            locator.click(button=button, click_count=count, modifiers=held, timeout=REF_TIMEOUT_MS)
            return

        with holding(tab.page.keyboard, held):
            tab.page.mouse.click(target.x, target.y, button=button, click_count=count)

    def left_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserLeftClickInput) -> None:
        self._click(input, "left", 1)

    def right_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserRightClickInput) -> None:
        self._click(input, "right", 1)

    def middle_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserMiddleClickInput) -> None:
        self._click(input, "middle", 1)

    def double_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserDoubleClickInput) -> None:
        self._click(input, "left", 2)

    def triple_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserTripleClickInput) -> None:
        self._click(input, "left", 3)

    def hover(self, context: BetaToolsetCallContext, input: beta.BetaBrowserHoverInput) -> None:
        tab = self._front(input.tab_id)
        target = input.target
        if isinstance(target, BetaBrowserRefTarget):
            self._element(tab, target.ref).hover(timeout=REF_TIMEOUT_MS)
        else:
            tab.page.mouse.move(target.x, target.y)

    def left_click_drag(self, context: BetaToolsetCallContext, input: beta.BetaBrowserLeftClickDragInput) -> None:
        mouse = self._front(input.tab_id).page.mouse
        mouse.move(input.from_.x, input.from_.y)
        mouse.down()
        try:
            mouse.move(input.target.x, input.target.y, steps=DRAG_STEPS)
        finally:  # a button left down would drag through every later action of the tab
            mouse.up()

    def left_mouse_down(self, context: BetaToolsetCallContext, input: beta.BetaBrowserLeftMouseDownInput) -> None:
        mouse = self._front(input.tab_id).page.mouse
        mouse.move(input.target.x, input.target.y)
        mouse.down()

    def left_mouse_up(self, context: BetaToolsetCallContext, input: beta.BetaBrowserLeftMouseUpInput) -> None:
        mouse = self._front(input.tab_id).page.mouse
        mouse.move(input.target.x, input.target.y)
        mouse.up()

    def mouse_move(self, context: BetaToolsetCallContext, input: beta.BetaBrowserMouseMoveInput) -> None:
        self._front(input.tab_id).page.mouse.move(input.target.x, input.target.y)

    def scroll(self, context: BetaToolsetCallContext, input: beta.BetaBrowserScrollInput) -> None:
        page = self._front(input.tab_id).page
        page.mouse.move(input.target.x, input.target.y)
        page.mouse.wheel(*given.wheel(input.scroll_direction, input.scroll_amount))
        page.wait_for_timeout(SCROLL_SETTLE_MS)

    def scroll_to(self, context: BetaToolsetCallContext, input: beta.BetaBrowserScrollToInput) -> None:
        tab = self._front(input.tab_id)
        self._element(tab, input.target.ref).scroll_into_view_if_needed(timeout=REF_TIMEOUT_MS)

    def type(self, context: BetaToolsetCallContext, input: beta.BetaBrowserTypeInput) -> None:
        self._front(input.tab_id).page.keyboard.type(input.text)

    def key(self, context: BetaToolsetCallContext, input: beta.BetaBrowserKeyInput) -> None:
        keyboard = self._front(input.tab_id).page.keyboard
        for keys in given.key_presses(input.text, input.repeat):
            press(keyboard, keys)

    def hold_key(self, context: BetaToolsetCallContext, input: beta.BetaBrowserHoldKeyInput) -> None:
        keys = given.chord_keys(input.text)
        duration_ms = given.milliseconds(input.duration)
        page = self._front(input.tab_id).page
        with holding(page.keyboard, keys):
            page.wait_for_timeout(duration_ms)

    def wait(self, context: BetaToolsetCallContext, input: beta.BetaBrowserWaitInput) -> None:
        self._tabs.get(input.tab_id).page.wait_for_timeout(given.milliseconds(input.duration))

    def read_page(self, context: BetaToolsetCallContext, input: beta.BetaBrowserReadPageInput) -> str:
        page = self._front(input.tab_id).page
        snapshot = page.aria_snapshot(mode="ai", boxes=True)
        view = ask(page, VIEWPORT)
        ref = None if input.ref is None else plain_ref(input.ref)
        return aria.read_page(
            snapshot, width=view["width"], height=view["height"], filter=input.filter, depth=input.depth, ref=ref
        )

    def get_page_text(self, context: BetaToolsetCallContext, input: beta.BetaBrowserGetPageTextInput) -> str:
        text = str(ask(self._front(input.tab_id).page, PAGE_TEXT))
        return aria.bounded(text, "read a part with read_page and its ref")

    def form_input(self, context: BetaToolsetCallContext, input: beta.BetaBrowserFormInputInput) -> None:
        element = self._element(self._front(input.tab_id), input.target.ref)
        kind = str(element.evaluate(FIELD_KIND, timeout=REF_TIMEOUT_MS))
        if kind in ("input:checkbox", "input:radio"):
            if not isinstance(input.value, bool):
                raise PageRefusal("value: a checkbox or a radio button takes true or false")
            element.set_checked(input.value, timeout=REF_TIMEOUT_MS)
        elif kind.startswith("select:"):
            element.select_option(given.form_text(input.value), timeout=REF_TIMEOUT_MS)
        else:
            element.fill(given.form_text(input.value), timeout=REF_TIMEOUT_MS)

    def javascript_exec(self, context: BetaToolsetCallContext, input: beta.BetaBrowserJavascriptExecInput) -> str:
        value = run_script(self._front(input.tab_id).page, input.text)
        return aria.bounded(json.dumps(value, ensure_ascii=False, default=str), "return less")

    def read_console(self, context: BetaToolsetCallContext, input: beta.BetaBrowserReadConsoleInput) -> str:
        return taken(self._front(input.tab_id).console)

    def read_network(self, context: BetaToolsetCallContext, input: beta.BetaBrowserReadNetworkInput) -> str:
        return taken(self._front(input.tab_id).network)

    def new_tab(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserNewTabInput
    ) -> BetaBrowserStateTabEntryParam:
        return self._entries([self._session.new_tab()])[0]

    def list_tabs(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserListTabsInput
    ) -> list[BetaBrowserStateTabEntryParam]:
        return self._entries(self._tabs.all)

    def switch_tab(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserSwitchTabInput
    ) -> BetaBrowserStateTabEntryParam:
        return self._entries([self._front(input.tab_id)])[0]

    def close_tab(self, context: BetaToolsetCallContext, input: beta.BetaBrowserCloseTabInput) -> None:
        self._session.close_tab(input.tab_id)
