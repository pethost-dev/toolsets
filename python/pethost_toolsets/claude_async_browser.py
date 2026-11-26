"""AsyncClaudeBrowser: ClaudeBrowser (claude_browser) for AsyncAnthropic, on Playwright's asyncio
API. It does what ClaudeBrowser does, in the same order; only the awaits differ, and a script of
javascript_exec, which asyncio gives up waiting for whatever keeps it (_async_page.run_script)."""

from __future__ import annotations

import base64
import json

from typing import Self

from anthropic import NOT_GIVEN, NotGiven
from anthropic.tools import ToolError, ToolsetUsageError
from anthropic.tools.browser import (
    BetaAsyncAbstractBrowserToolset20260801,
    BetaAsyncConfirmCallable,
    BetaAsyncURLPolicy,
    BetaBrowserMemberResult,
    BetaBrowserNavigateResult,
    BetaBrowserState,
    BetaScreenshotResult,
    BetaToolConfigs,
    BetaToolsetCallContext,
)
from anthropic.types import beta
from anthropic.types.beta import BetaBrowserRefTarget, BetaBrowserStateTabEntryParam
from pethost.sandboxes import AsyncSandboxes, SandboxesError
from playwright.async_api import Error, Locator, Page

from . import _aria as aria
from . import _browser_input as given
from ._async_page import ask, go, holding, press, run_script
from ._async_session import AsyncSession
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
from ._tabs import Tab, taken


class AsyncClaudeBrowser(BetaAsyncAbstractBrowserToolset20260801):
    """The browser toolset on one sandbox's Chrome, for AsyncAnthropic. Make it with
    `await AsyncClaudeBrowser.connect(sandboxes, sandbox_id)`; close() disconnects and leaves the
    browser running in the sandbox."""

    def __init__(
        self,
        *,
        configs: beta.BetaBrowserToolsetConfigsParam | None = None,
        confirm: BetaAsyncConfirmCallable | None = None,
        url_policy: BetaAsyncURLPolicy | NotGiven = NOT_GIVEN,
        tool_configs: BetaToolConfigs | None = None,
    ) -> None:
        """The SDK's options (find and file_upload stay off). connect() takes the same."""
        super().__init__(
            configs=served_configs(configs), confirm=confirm, url_policy=url_policy, tool_configs=tool_configs
        )
        self._session = AsyncSession()
        self._tabs = self._session.tabs
        self._link = self._session.link

    @classmethod
    async def connect(
        cls,
        sandboxes: AsyncSandboxes,
        sandbox_id: str,
        *,
        link_ttl_seconds: int = LINK_TTL_SECONDS,
        configs: beta.BetaBrowserToolsetConfigsParam | None = None,
        confirm: BetaAsyncConfirmCallable | None = None,
        url_policy: BetaAsyncURLPolicy | NotGiven = NOT_GIVEN,
        tool_configs: BetaToolConfigs | None = None,
    ) -> Self:
        """Connects to the sandbox's browser: see ClaudeBrowser.connect."""
        toolset = cls(configs=configs, confirm=confirm, url_policy=url_policy, tool_configs=tool_configs)
        try:
            await toolset._session.open(sandboxes, sandbox_id, link_ttl_seconds)
        except BaseException:
            await toolset.close()
            raise
        return toolset

    async def close(self) -> None:
        await super().close()
        await self._session.close()

    async def _ready(self) -> None:
        """The connection a member needs, made again when it dropped: see ClaudeBrowser._ready."""
        if not self._session.opened:
            raise ToolsetUsageError("Make the browser toolset with connect().")
        try:
            await self._session.ready()
        except (SandboxesError, BrowserConnectionError) as error:
            raise ToolError(str(error)) from None

    async def execute(
        self, context: BetaToolsetCallContext, name: beta.BetaBrowserMemberName, input: beta.BetaBrowserMemberInput
    ) -> BetaBrowserMemberResult:
        failure = ""
        try:
            await self._ready()
            return await super().execute(context, name, input)
        except PageRefusal as refusal:
            failure = str(refusal)
        except Error as error:
            failure = error_text(error, self._link.secret) if self._link.connected() else LOST
        raise ToolError(failure)

    async def _browser_state(self, context: BetaToolsetCallContext) -> BetaBrowserState:
        """The tabs after a call: see ClaudeBrowser._browser_state."""
        changes = state_changes(self._tabs.drain())
        if not self._link.connected():
            return BetaBrowserState(tabs=[], state_changes=[*changes])
        return BetaBrowserState(tabs=await self._entries(self._tabs.all), state_changes=[*changes])

    async def _front(self, tab_id: str | None) -> Tab[Page]:
        return await self._session.front(tab_id)

    async def _element(self, tab: Tab[Page], ref: str) -> Locator:
        return await self._session.element(tab, ref)

    async def _entries(self, tabs: list[Tab[Page]]) -> list[BetaBrowserStateTabEntryParam]:
        """The tabs as the browser state lists them, their titles as the browser reads them."""
        pairs = await self._session.titles(tabs)
        return [tab_entry(tab, title, tab.page.url, self._tabs.active) for tab, title in pairs]

    async def navigate(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserNavigateInput
    ) -> BetaBrowserNavigateResult:
        tab = await self._front(input.tab_id)
        response = await go(tab.page, input.url)
        status = response.status if response is not None else None
        entry = (await self._entries([tab]))[0]
        return BetaBrowserNavigateResult(url=entry["url"], status=status, title=entry["title"] or None)

    async def screenshot(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserScreenshotInput
    ) -> BetaScreenshotResult:
        image = await (await self._front(input.tab_id)).page.screenshot(type="png", scale="css")
        return BetaScreenshotResult(data=base64.b64encode(image).decode("ascii"))

    async def zoom(self, context: BetaToolsetCallContext, input: beta.BetaBrowserZoomInput) -> BetaScreenshotResult:
        page = (await self._front(input.tab_id)).page
        view = await ask(page, VIEWPORT)
        clip = given.zoom_clip(input.region, view["x"], view["y"], view["width"], view["height"])
        return BetaScreenshotResult(data=await self._link.capture(page, clip))

    async def _click(self, input: ClickInput, button: given.Button, count: int) -> None:
        tab = await self._front(input.tab_id)
        held = given.modifiers(input.modifiers)
        target = input.target
        if isinstance(target, BetaBrowserRefTarget):
            locator = await self._element(tab, target.ref)
            await locator.click(button=button, click_count=count, modifiers=held, timeout=REF_TIMEOUT_MS)
            return

        async with holding(tab.page.keyboard, held):
            await tab.page.mouse.click(target.x, target.y, button=button, click_count=count)

    async def left_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserLeftClickInput) -> None:
        await self._click(input, "left", 1)

    async def right_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserRightClickInput) -> None:
        await self._click(input, "right", 1)

    async def middle_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserMiddleClickInput) -> None:
        await self._click(input, "middle", 1)

    async def double_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserDoubleClickInput) -> None:
        await self._click(input, "left", 2)

    async def triple_click(self, context: BetaToolsetCallContext, input: beta.BetaBrowserTripleClickInput) -> None:
        await self._click(input, "left", 3)

    async def hover(self, context: BetaToolsetCallContext, input: beta.BetaBrowserHoverInput) -> None:
        tab = await self._front(input.tab_id)
        target = input.target
        if isinstance(target, BetaBrowserRefTarget):
            await (await self._element(tab, target.ref)).hover(timeout=REF_TIMEOUT_MS)
        else:
            await tab.page.mouse.move(target.x, target.y)

    async def left_click_drag(self, context: BetaToolsetCallContext, input: beta.BetaBrowserLeftClickDragInput) -> None:
        mouse = (await self._front(input.tab_id)).page.mouse
        await mouse.move(input.from_.x, input.from_.y)
        await mouse.down()
        try:
            await mouse.move(input.target.x, input.target.y, steps=DRAG_STEPS)
        finally:  # a button left down would drag through every later action of the tab
            await mouse.up()

    async def left_mouse_down(self, context: BetaToolsetCallContext, input: beta.BetaBrowserLeftMouseDownInput) -> None:
        mouse = (await self._front(input.tab_id)).page.mouse
        await mouse.move(input.target.x, input.target.y)
        await mouse.down()

    async def left_mouse_up(self, context: BetaToolsetCallContext, input: beta.BetaBrowserLeftMouseUpInput) -> None:
        mouse = (await self._front(input.tab_id)).page.mouse
        await mouse.move(input.target.x, input.target.y)
        await mouse.up()

    async def mouse_move(self, context: BetaToolsetCallContext, input: beta.BetaBrowserMouseMoveInput) -> None:
        await (await self._front(input.tab_id)).page.mouse.move(input.target.x, input.target.y)

    async def scroll(self, context: BetaToolsetCallContext, input: beta.BetaBrowserScrollInput) -> None:
        page = (await self._front(input.tab_id)).page
        await page.mouse.move(input.target.x, input.target.y)
        await page.mouse.wheel(*given.wheel(input.scroll_direction, input.scroll_amount))
        await page.wait_for_timeout(SCROLL_SETTLE_MS)

    async def scroll_to(self, context: BetaToolsetCallContext, input: beta.BetaBrowserScrollToInput) -> None:
        tab = await self._front(input.tab_id)
        await (await self._element(tab, input.target.ref)).scroll_into_view_if_needed(timeout=REF_TIMEOUT_MS)

    async def type(self, context: BetaToolsetCallContext, input: beta.BetaBrowserTypeInput) -> None:
        await (await self._front(input.tab_id)).page.keyboard.type(input.text)

    async def key(self, context: BetaToolsetCallContext, input: beta.BetaBrowserKeyInput) -> None:
        keyboard = (await self._front(input.tab_id)).page.keyboard
        for keys in given.key_presses(input.text, input.repeat):
            await press(keyboard, keys)

    async def hold_key(self, context: BetaToolsetCallContext, input: beta.BetaBrowserHoldKeyInput) -> None:
        keys = given.chord_keys(input.text)
        duration_ms = given.milliseconds(input.duration)
        page = (await self._front(input.tab_id)).page
        async with holding(page.keyboard, keys):
            await page.wait_for_timeout(duration_ms)

    async def wait(self, context: BetaToolsetCallContext, input: beta.BetaBrowserWaitInput) -> None:
        await self._tabs.get(input.tab_id).page.wait_for_timeout(given.milliseconds(input.duration))

    async def read_page(self, context: BetaToolsetCallContext, input: beta.BetaBrowserReadPageInput) -> str:
        page = (await self._front(input.tab_id)).page
        snapshot = await page.aria_snapshot(mode="ai", boxes=True)
        view = await ask(page, VIEWPORT)
        ref = None if input.ref is None else plain_ref(input.ref)
        return aria.read_page(
            snapshot, width=view["width"], height=view["height"], filter=input.filter, depth=input.depth, ref=ref
        )

    async def get_page_text(self, context: BetaToolsetCallContext, input: beta.BetaBrowserGetPageTextInput) -> str:
        text = str(await ask((await self._front(input.tab_id)).page, PAGE_TEXT))
        return aria.bounded(text, "read a part with read_page and its ref")

    async def form_input(self, context: BetaToolsetCallContext, input: beta.BetaBrowserFormInputInput) -> None:
        element = await self._element(await self._front(input.tab_id), input.target.ref)
        kind = str(await element.evaluate(FIELD_KIND, timeout=REF_TIMEOUT_MS))
        if kind in ("input:checkbox", "input:radio"):
            if not isinstance(input.value, bool):
                raise PageRefusal("value: a checkbox or a radio button takes true or false")
            await element.set_checked(input.value, timeout=REF_TIMEOUT_MS)
        elif kind.startswith("select:"):
            await element.select_option(given.form_text(input.value), timeout=REF_TIMEOUT_MS)
        else:
            await element.fill(given.form_text(input.value), timeout=REF_TIMEOUT_MS)

    async def javascript_exec(self, context: BetaToolsetCallContext, input: beta.BetaBrowserJavascriptExecInput) -> str:
        value = await run_script((await self._front(input.tab_id)).page, input.text)
        return aria.bounded(json.dumps(value, ensure_ascii=False, default=str), "return less")

    async def read_console(self, context: BetaToolsetCallContext, input: beta.BetaBrowserReadConsoleInput) -> str:
        return taken((await self._front(input.tab_id)).console)

    async def read_network(self, context: BetaToolsetCallContext, input: beta.BetaBrowserReadNetworkInput) -> str:
        return taken((await self._front(input.tab_id)).network)

    async def new_tab(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserNewTabInput
    ) -> BetaBrowserStateTabEntryParam:
        return (await self._entries([await self._session.new_tab()]))[0]

    async def list_tabs(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserListTabsInput
    ) -> list[BetaBrowserStateTabEntryParam]:
        return await self._entries(self._tabs.all)

    async def switch_tab(
        self, context: BetaToolsetCallContext, input: beta.BetaBrowserSwitchTabInput
    ) -> BetaBrowserStateTabEntryParam:
        return (await self._entries([await self._front(input.tab_id)]))[0]

    async def close_tab(self, context: BetaToolsetCallContext, input: beta.BetaBrowserCloseTabInput) -> None:
        await self._session.close_tab(input.tab_id)
