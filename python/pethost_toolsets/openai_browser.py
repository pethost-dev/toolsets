"""A driver of the openai SDK's BrowserToolset (openai.lib.browser) on the Chrome of a sandbox's
desktop, through Playwright over the sandbox's browser link: OpenAIBrowser, synchronous.
AsyncOpenAIBrowser, for AsyncBrowserToolset, is in openai_async_browser and does the same in the
same order.

It is the browser Claude's driver (claude_browser) drives, over the same connection and tabs
(_sync_session), with the members in OpenAI's words: read_page gives Playwright's snapshot of the
page, whose refs (e5, f1e2) click, type, select_option, hover, scroll_to and set_checked take. find
is not served (it matches a description in words, which takes a model), nor upload_file and
download_file (the browser is not on the machine the files are). What a member cannot do reaches the
model as the SDK's BrowserError, in the page's or the sandbox's words, and what happened beside it
(a tab the page opened, a dialog dismissed) is its result."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
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
from pethost.sandboxes import Sandboxes, SandboxesError
from playwright.sync_api import Error, Locator, Page, TimeoutError

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
from ._sync_page import ask, go, holding, press, run_script
from ._sync_session import SyncSession


class OpenAIBrowser:
    """The sandbox's Chrome as a BrowserToolset's driver. Make it with OpenAIBrowser.connect(sandboxes,
    sandbox_id) and pass it to BrowserToolset; close() disconnects and leaves the browser running in
    the sandbox. Use it from the thread that made it, as Playwright's synchronous API asks."""

    def __init__(self) -> None:
        """A driver with no browser yet: connect() makes one that has it."""
        self._session = SyncSession()
        self._tabs = self._session.tabs

    @classmethod
    def connect(cls, sandboxes: Sandboxes, sandbox_id: str, *, link_ttl_seconds: int = LINK_TTL_SECONDS) -> Self:
        """Connects to the sandbox's browser, starting its desktop when it does not run (some seconds).
        `link_ttl_seconds` is how long each link may open its connection, which then lasts until
        close(). A link the server refuses (a stopped sandbox) raises BrowserConnectionError with the
        server's words."""
        driver = cls()
        try:
            driver._session.open(sandboxes, sandbox_id, link_ttl_seconds)
        except BaseException:
            driver.close()
            raise
        return driver

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, kind: type[BaseException] | None, error: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    @contextmanager
    def _acting(self) -> Generator[None]:
        """A member's work, on a connection made again if it dropped, its failures as BrowserError."""
        with shape.refusals(self._session.link):
            self._session.ready()
            yield

    def _done(self, opened_here: str = "") -> str | None:
        """An action's result: what happened beside it since the last one."""
        return shape.notes(self._tabs.drain(), opened_here)

    def state(self) -> BrowserState:
        """The open tabs, which the SDK reads before and after each member; none while the browser
        cannot be reached, which the member then says, rather than an error that ends the run."""
        try:
            self._session.ready()
            pairs = self._session.titles(self._tabs.all)
        except (BrowserConnectionError, SandboxesError, Error):
            return {"tabs": []}
        return shape.state([(tab, title, tab.page.url) for tab, title in pairs], self._tabs.active)

    def _page(self, tab_id: str | None) -> Page:
        return self._session.front(tab_id).page

    def _element(self, tab_id: str | None, target: str) -> Locator:
        """The element of a ref, in the tab it names, made the active one."""
        return self._session.element(self._session.front(tab_id), target)

    def _view(self, page: Page) -> tuple[float, float]:
        view = ask(page, VIEWPORT)
        return float(view["width"]), float(view["height"])

    def navigate(self, action: NavigateInput) -> str | None:
        with self._acting():
            response = go(self._page(action["tab_id"]), action["url"])
            failed = response is not None and response.status >= 400
            status = f"The page answered HTTP {response.status}." if response is not None and failed else None
            return "\n".join(line for line in (status, self._done()) if line) or None

    def read_page(self, action: ReadPageInput) -> str:
        with self._acting():
            page = self._page(action["tab_id"])
            snapshot = page.aria_snapshot(mode="ai", boxes=True)
            width, height = self._view(page)
            return aria.read_page(snapshot, width=width, height=height, filter=action["filter"], depth=None, ref=None)

    def get_page_text(self, action: TabInput) -> str:
        with self._acting():
            text = str(ask(self._page(action["tab_id"]), PAGE_TEXT))
            return aria.bounded(text, "read the page with read_page")

    def click(self, action: ClickInput) -> str | None:
        with self._acting():
            self._element(action["tab_id"], action["target"]).click(timeout=REF_TIMEOUT_MS)
            return self._done()

    def type(self, action: TypeInput) -> str | None:
        with self._acting():
            target = action["target"]
            if target is None:
                self._page(action["tab_id"]).keyboard.type(action["text"])
            else:
                self._element(action["tab_id"], target).fill(action["text"], timeout=REF_TIMEOUT_MS)
            return self._done()

    def key(self, action: KeyInput) -> str | None:
        with self._acting():
            press(self._page(action["tab_id"]).keyboard, shape.keys(action["keys"]))
            return self._done()

    def scroll(self, action: ScrollInput) -> str | None:
        with self._acting():
            page = self._page(action["tab_id"])
            width, height = self._view(page)
            page.mouse.move(width / 2, height / 2)  # the wheel scrolls what is under the pointer
            page.mouse.wheel(*shape.scroll(action["direction"], action["amount"], width, height))
            page.wait_for_timeout(SCROLL_SETTLE_MS)
            return self._done()

    def scroll_to(self, action: ClickInput) -> str | None:
        with self._acting():
            self._element(action["tab_id"], action["target"]).scroll_into_view_if_needed(timeout=REF_TIMEOUT_MS)
            return self._done()

    def wait_for(self, action: WaitForInput) -> str | None:
        text = shape.wait_text(action["text"])
        with self._acting():
            page = self._session.tabs.get(action["tab_id"]).page
            try:
                page.get_by_text(text).first.wait_for(state="visible", timeout=action["timeout_ms"])
            except TimeoutError:
                raise PageRefusal(f"No visible text {text!r} within {action['timeout_ms']} ms.") from None
            return None

    def select_option(self, action: SelectOptionInput) -> str | None:
        with self._acting():
            self._element(action["tab_id"], action["target"]).select_option(action["values"], timeout=REF_TIMEOUT_MS)
            return self._done()

    def hover(self, action: ClickInput) -> str | None:
        with self._acting():
            self._element(action["tab_id"], action["target"]).hover(timeout=REF_TIMEOUT_MS)
            return self._done()

    def screenshot(self, action: TabInput) -> ResponseInputImageContentParam:
        with self._acting():
            return shape.image(self._page(action["tab_id"]).screenshot(type="png", scale="css"))

    def zoom(self, action: ZoomInput) -> ResponseInputImageContentParam:
        with self._acting():
            page = self._page(action["tab_id"])
            view = ask(page, VIEWPORT)
            shape.region(action["region"], view["width"], view["height"])
            clip = given.zoom_clip(action["region"], view["x"], view["y"], view["width"], view["height"])
            return shape.image(self._session.link.capture(page, clip))

    def new_tab(self, action: NewTabInput) -> str | None:
        with self._acting():
            tab = self._session.new_tab()
            if action["url"] is not None:
                go(tab.page, action["url"])
            return self._done(opened_here=tab.tab_id)

    def switch_tab(self, action: TabInput) -> str | None:
        with self._acting():
            self._session.front(action["tab_id"])
            return self._done()

    def close_tab(self, action: TabInput) -> str | None:
        with self._acting():
            tab_id = action["tab_id"]
            if tab_id is None:
                raise PageRefusal("tab_id: name the tab to close")
            self._session.close_tab(tab_id)
            return self._done()

    def click_at(self, action: ClickAtInput) -> str | None:
        with self._acting():
            page = self._page(action["tab_id"])
            shape.inside([(action["x"], action["y"])], *self._view(page))
            with holding(page.keyboard, action["keys"]):
                page.mouse.click(action["x"], action["y"], button=action["button"], click_count=action["click_count"])
            return self._done()

    def hover_at(self, action: HoverAtInput) -> str | None:
        with self._acting():
            page = self._page(action["tab_id"])
            shape.inside([(action["x"], action["y"])], *self._view(page))
            page.mouse.move(action["x"], action["y"])
            return self._done()

    def drag_path(self, action: DragPathInput) -> str | None:
        with self._acting():
            page = self._page(action["tab_id"])
            first, *rest = action["path"]
            shape.inside([(point["x"], point["y"]) for point in action["path"]], *self._view(page))
            with holding(page.keyboard, action["keys"]):
                page.mouse.move(first["x"], first["y"])
                page.mouse.down()
                try:
                    for point in rest:
                        page.mouse.move(point["x"], point["y"], steps=DRAG_STEPS)
                finally:  # a button left down would drag through every later action of the tab
                    page.mouse.up()
            return self._done()

    def hold_keys(self, action: HoldKeysInput) -> str | None:
        with self._acting():
            page = self._page(action["tab_id"])
            with holding(page.keyboard, shape.keys(action["keys"])):
                page.wait_for_timeout(action["duration_ms"])
            return self._done()

    def set_checked(self, action: SetCheckedInput) -> str | None:
        with self._acting():
            self._element(action["tab_id"], action["target"]).set_checked(action["checked"], timeout=REF_TIMEOUT_MS)
            return self._done()

    def read_diagnostics(self, action: ReadDiagnosticsInput) -> BrowserReadV1:
        with self._acting():
            tab = self._session.front(action["tab_id"])
            lines = tab.console if action["source"] == "console" else tab.network
            taken = list(lines)
            lines.clear()
            return shape.diagnostics(taken, action["limit"], action["source"])

    def run_script(self, action: RunScriptInput) -> str:
        with self._acting():
            value = run_script(self._page(action["tab_id"]), action["source"], action["timeout_ms"])
            return shape.unicode(aria.bounded(json.dumps(value, ensure_ascii=False, default=str), "return less"))
