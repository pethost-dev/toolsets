"""AsyncOpenAIBrowser: OpenAIBrowser (openai_browser) for the openai SDK's AsyncBrowserToolset, on
Playwright's asyncio API. It does what OpenAIBrowser does, in the same order; only the awaits
differ, and a page script, which asyncio gives up waiting for whatever keeps it
(_async_page.run_script)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Self

from openai.lib.browser import (
    BrowserReadV1,
    BrowserState,
    ClickAtInput,
    ClickInput,
    DragPathInput,
    HoldKeysInput,
    HoverAtInput,
    KeyInput,
    NavigateInput,
    NewTabInput,
    ReadDiagnosticsInput,
    ReadPageInput,
    RunScriptInput,
    ScrollInput,
    SelectOptionInput,
    SetCheckedInput,
    TabInput,
    TypeInput,
    WaitForInput,
    ZoomInput,
)
from openai.types.responses.response_input_image_content_param import ResponseInputImageContentParam
from pethost.sandboxes import AsyncSandboxes, SandboxesError
from playwright.async_api import Error, Locator, Page, TimeoutError

from . import _aria as aria
from . import _browser_input as given
from . import _openai_browser as shape
from ._browser_shared import (
    DRAG_STEPS,
    LINK_TTL_SECONDS,
    PAGE_TEXT,
    REF_TIMEOUT_MS,
    SCROLL_SETTLE_MS,
    VIEWPORT,
    BrowserConnectionError,
    PageRefusal,
)
from ._async_page import ask, go, holding, press, run_script
from ._async_session import AsyncSession


class AsyncOpenAIBrowser:
    """The sandbox's Chrome as an AsyncBrowserToolset's driver. Make it with
    `await AsyncOpenAIBrowser.connect(sandboxes, sandbox_id)` and pass it to AsyncBrowserToolset;
    close() disconnects and leaves the browser running in the sandbox."""

    def __init__(self) -> None:
        """A driver with no browser yet: connect() makes one that has it."""
        self._session = AsyncSession()
        self._tabs = self._session.tabs

    @classmethod
    async def connect(
        cls, sandboxes: AsyncSandboxes, sandbox_id: str, *, link_ttl_seconds: int = LINK_TTL_SECONDS
    ) -> Self:
        """Connects to the sandbox's browser: see OpenAIBrowser.connect."""
        driver = cls()
        try:
            await driver._session.open(sandboxes, sandbox_id, link_ttl_seconds)
        except BaseException:
            await driver.close()
            raise
        return driver

    async def close(self) -> None:
        await self._session.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.close()

    @asynccontextmanager
    async def _acting(self) -> AsyncGenerator[None]:
        """A member's work, on a connection made again if it dropped, its failures as BrowserError."""
        with shape.refusals(self._session.link):
            await self._session.ready()
            yield

    def _done(self, opened_here: str = "") -> str | None:
        """An action's result: what happened beside it since the last one."""
        return shape.notes(self._tabs.drain(), opened_here)

    async def state(self) -> BrowserState:
        """The open tabs, which the SDK reads before and after each member; none while the browser
        cannot be reached, which the member then says, rather than an error that ends the run."""
        try:
            await self._session.ready()
            pairs = await self._session.titles(self._tabs.all)
        except (BrowserConnectionError, SandboxesError, Error):
            return {"tabs": []}
        return shape.state([(tab, title, tab.page.url) for tab, title in pairs], self._tabs.active)

    async def _page(self, tab_id: str | None) -> Page:
        return (await self._session.front(tab_id)).page

    async def _element(self, tab_id: str | None, target: str) -> Locator:
        """The element of a ref, in the tab it names, made the active one."""
        return await self._session.element(await self._session.front(tab_id), target)

    async def _view(self, page: Page) -> tuple[float, float]:
        view = await ask(page, VIEWPORT)
        return float(view["width"]), float(view["height"])

    async def navigate(self, action: NavigateInput) -> str | None:
        async with self._acting():
            response = await go(await self._page(action["tab_id"]), action["url"])
            failed = response is not None and response.status >= 400
            status = f"The page answered HTTP {response.status}." if response is not None and failed else None
            return "\n".join(line for line in (status, self._done()) if line) or None

    async def read_page(self, action: ReadPageInput) -> str:
        async with self._acting():
            page = await self._page(action["tab_id"])
            snapshot = await page.aria_snapshot(mode="ai", boxes=True)
            width, height = await self._view(page)
            return aria.read_page(snapshot, width=width, height=height, filter=action["filter"], depth=None, ref=None)

    async def get_page_text(self, action: TabInput) -> str:
        async with self._acting():
            text = str(await ask(await self._page(action["tab_id"]), PAGE_TEXT))
            return aria.bounded(text, "read the page with read_page")

    async def click(self, action: ClickInput) -> str | None:
        async with self._acting():
            element = await self._element(action["tab_id"], action["target"])
            await element.click(timeout=REF_TIMEOUT_MS)
            return self._done()

    async def type(self, action: TypeInput) -> str | None:
        async with self._acting():
            target = action["target"]
            if target is None:
                await (await self._page(action["tab_id"])).keyboard.type(action["text"])
            else:
                element = await self._element(action["tab_id"], target)
                await element.fill(action["text"], timeout=REF_TIMEOUT_MS)
            return self._done()

    async def key(self, action: KeyInput) -> str | None:
        async with self._acting():
            page = await self._page(action["tab_id"])
            await press(page.keyboard, shape.keys(action["keys"]))
            return self._done()

    async def scroll(self, action: ScrollInput) -> str | None:
        async with self._acting():
            page = await self._page(action["tab_id"])
            width, height = await self._view(page)
            await page.mouse.move(width / 2, height / 2)  # the wheel scrolls what is under the pointer
            await page.mouse.wheel(*shape.scroll(action["direction"], action["amount"], width, height))
            await page.wait_for_timeout(SCROLL_SETTLE_MS)
            return self._done()

    async def scroll_to(self, action: ClickInput) -> str | None:
        async with self._acting():
            element = await self._element(action["tab_id"], action["target"])
            await element.scroll_into_view_if_needed(timeout=REF_TIMEOUT_MS)
            return self._done()

    async def wait_for(self, action: WaitForInput) -> str | None:
        text = shape.wait_text(action["text"])
        async with self._acting():
            page = self._session.tabs.get(action["tab_id"]).page
            try:
                await page.get_by_text(text).first.wait_for(state="visible", timeout=action["timeout_ms"])
            except TimeoutError:
                raise PageRefusal(f"No visible text {text!r} within {action['timeout_ms']} ms.") from None
            return None

    async def select_option(self, action: SelectOptionInput) -> str | None:
        async with self._acting():
            element = await self._element(action["tab_id"], action["target"])
            await element.select_option(action["values"], timeout=REF_TIMEOUT_MS)
            return self._done()

    async def hover(self, action: ClickInput) -> str | None:
        async with self._acting():
            element = await self._element(action["tab_id"], action["target"])
            await element.hover(timeout=REF_TIMEOUT_MS)
            return self._done()

    async def screenshot(self, action: TabInput) -> ResponseInputImageContentParam:
        async with self._acting():
            page = await self._page(action["tab_id"])
            return shape.image(await page.screenshot(type="png", scale="css"))

    async def zoom(self, action: ZoomInput) -> ResponseInputImageContentParam:
        async with self._acting():
            page = await self._page(action["tab_id"])
            view = await ask(page, VIEWPORT)
            shape.region(action["region"], view["width"], view["height"])
            clip = given.zoom_clip(action["region"], view["x"], view["y"], view["width"], view["height"])
            return shape.image(await self._session.link.capture(page, clip))

    async def new_tab(self, action: NewTabInput) -> str | None:
        async with self._acting():
            tab = await self._session.new_tab()
            if action["url"] is not None:
                await go(tab.page, action["url"])
            return self._done(opened_here=tab.tab_id)

    async def switch_tab(self, action: TabInput) -> str | None:
        async with self._acting():
            await self._session.front(action["tab_id"])
            return self._done()

    async def close_tab(self, action: TabInput) -> str | None:
        async with self._acting():
            tab_id = action["tab_id"]
            if tab_id is None:
                raise PageRefusal("tab_id: name the tab to close")
            await self._session.close_tab(tab_id)
            return self._done()

    async def click_at(self, action: ClickAtInput) -> str | None:
        async with self._acting():
            page = await self._page(action["tab_id"])
            shape.inside([(action["x"], action["y"])], *await self._view(page))
            async with holding(page.keyboard, action["keys"]):
                await page.mouse.click(
                    action["x"], action["y"], button=action["button"], click_count=action["click_count"]
                )
            return self._done()

    async def hover_at(self, action: HoverAtInput) -> str | None:
        async with self._acting():
            page = await self._page(action["tab_id"])
            shape.inside([(action["x"], action["y"])], *await self._view(page))
            await page.mouse.move(action["x"], action["y"])
            return self._done()

    async def drag_path(self, action: DragPathInput) -> str | None:
        async with self._acting():
            page = await self._page(action["tab_id"])
            first, *rest = action["path"]
            shape.inside([(point["x"], point["y"]) for point in action["path"]], *await self._view(page))
            async with holding(page.keyboard, action["keys"]):
                await page.mouse.move(first["x"], first["y"])
                await page.mouse.down()
                try:
                    for point in rest:
                        await page.mouse.move(point["x"], point["y"], steps=DRAG_STEPS)
                finally:  # a button left down would drag through every later action of the tab
                    await page.mouse.up()
            return self._done()

    async def hold_keys(self, action: HoldKeysInput) -> str | None:
        async with self._acting():
            page = await self._page(action["tab_id"])
            async with holding(page.keyboard, shape.keys(action["keys"])):
                await page.wait_for_timeout(action["duration_ms"])
            return self._done()

    async def set_checked(self, action: SetCheckedInput) -> str | None:
        async with self._acting():
            element = await self._element(action["tab_id"], action["target"])
            await element.set_checked(action["checked"], timeout=REF_TIMEOUT_MS)
            return self._done()

    async def read_diagnostics(self, action: ReadDiagnosticsInput) -> BrowserReadV1:
        async with self._acting():
            tab = await self._session.front(action["tab_id"])
            lines = tab.console if action["source"] == "console" else tab.network
            taken = list(lines)
            lines.clear()
            return shape.diagnostics(taken, action["limit"], action["source"])

    async def run_script(self, action: RunScriptInput) -> str:
        async with self._acting():
            value = await run_script(await self._page(action["tab_id"]), action["source"], action["timeout_ms"])
            return shape.unicode(aria.bounded(json.dumps(value, ensure_ascii=False, default=str), "return less"))
