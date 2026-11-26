"""Claude's computer toolset (computer_toolset_20260801) on a sandbox's desktop: ClaudeComputer
for Anthropic, AsyncClaudeComputer for AsyncAnthropic. Every member is one ControlDesktop call
(_claude_computer_plan), and what the desktop refuses reaches Claude as the desktop's own words."""

from __future__ import annotations

from typing import Literal

from anthropic.tools import ToolError
from anthropic.tools.computer import (
    BetaAbstractComputerToolset20260801,
    BetaAsyncAbstractComputerToolset20260801,
    BetaAsyncComputerConfirmCallable,
    BetaComputerConfirmCallable,
    BetaComputerCursorPositionResult,
    BetaScreenshotResult,
    BetaToolConfigs,
    BetaToolsetCallContext,
)
from anthropic.types.beta import (
    BetaComputerCursorPositionInput,
    BetaComputerDoubleClickInput,
    BetaComputerHoldKeyInput,
    BetaComputerKeyInput,
    BetaComputerLeftClickDragInput,
    BetaComputerLeftClickInput,
    BetaComputerLeftMouseDownInput,
    BetaComputerLeftMouseUpInput,
    BetaComputerMiddleClickInput,
    BetaComputerMouseMoveInput,
    BetaComputerRightClickInput,
    BetaComputerScreenshotInput,
    BetaComputerScrollInput,
    BetaComputerToolsetConfigsParam,
    BetaComputerTripleClickInput,
    BetaComputerTypeInput,
    BetaComputerWaitInput,
    BetaComputerZoomInput,
)
from pethost.sandboxes import AsyncSandboxes, ControlDesktopResponse, MouseButton, Sandboxes, SandboxesError

from . import _claude_computer_plan as plan
from ._desktop import DesktopCall, DesktopRefusedError, base64_image, check, image

LEFT, RIGHT, MIDDLE = MouseButton.LEFT, MouseButton.RIGHT, MouseButton.MIDDLE


class ClaudeComputer(BetaAbstractComputerToolset20260801):
    """The computer toolset on the desktop of one sandbox, through a Sandboxes client.

    `confirm` is the SDK's: asked before every call, and required while `type`, `key` or
    `hold_key` is on. The client stays the caller's: close() leaves it open.
    """

    def __init__(
        self,
        sandboxes: Sandboxes,
        sandbox_id: str,
        *,
        confirm: BetaComputerConfirmCallable | None,
        configs: BetaComputerToolsetConfigsParam | None = None,
        tool_configs: BetaToolConfigs | None = None,
    ) -> None:
        super().__init__(configs=configs, confirm=confirm, tool_configs=tool_configs)
        self._sandboxes = sandboxes
        self._sandbox_id = sandbox_id

    def _do(self, call: DesktopCall) -> ControlDesktopResponse:
        try:
            answer = self._sandboxes.control_desktop(
                self._sandbox_id, actions=call.actions, skip_screenshot=not call.image, screenshot_region=call.region
            )
            return check(answer, call)
        except SandboxesError as error:
            raise ToolError(error.message or type(error).__name__) from None
        except DesktopRefusedError as error:
            raise ToolError(error.message) from None

    def screenshot(self, context: BetaToolsetCallContext, input: BetaComputerScreenshotInput) -> BetaScreenshotResult:
        return screenshot_result(self._do(plan.screenshot()))

    def zoom(self, context: BetaToolsetCallContext, input: BetaComputerZoomInput) -> BetaScreenshotResult:
        return screenshot_result(self._do(plan.zoom(input)))

    def cursor_position(
        self, context: BetaToolsetCallContext, input: BetaComputerCursorPositionInput
    ) -> BetaComputerCursorPositionResult:
        return cursor_result(self._do(plan.cursor_position()))

    def left_click(self, context: BetaToolsetCallContext, input: BetaComputerLeftClickInput) -> None:
        self._do(plan.click(input, LEFT, 1))

    def right_click(self, context: BetaToolsetCallContext, input: BetaComputerRightClickInput) -> None:
        self._do(plan.click(input, RIGHT, 1))

    def middle_click(self, context: BetaToolsetCallContext, input: BetaComputerMiddleClickInput) -> None:
        self._do(plan.click(input, MIDDLE, 1))

    def double_click(self, context: BetaToolsetCallContext, input: BetaComputerDoubleClickInput) -> None:
        self._do(plan.click(input, LEFT, 2))

    def triple_click(self, context: BetaToolsetCallContext, input: BetaComputerTripleClickInput) -> None:
        self._do(plan.click(input, LEFT, 3))

    def left_click_drag(self, context: BetaToolsetCallContext, input: BetaComputerLeftClickDragInput) -> None:
        self._do(plan.left_click_drag(input))

    def mouse_move(self, context: BetaToolsetCallContext, input: BetaComputerMouseMoveInput) -> None:
        self._do(plan.mouse_move(input))

    def left_mouse_down(self, context: BetaToolsetCallContext, input: BetaComputerLeftMouseDownInput) -> None:
        self._do(plan.left_mouse_down())

    def left_mouse_up(self, context: BetaToolsetCallContext, input: BetaComputerLeftMouseUpInput) -> None:
        self._do(plan.left_mouse_up())

    def scroll(self, context: BetaToolsetCallContext, input: BetaComputerScrollInput) -> None:
        self._do(plan.scroll(input))

    def type(self, context: BetaToolsetCallContext, input: BetaComputerTypeInput) -> None:
        self._do(plan.type_text(input))

    def key(self, context: BetaToolsetCallContext, input: BetaComputerKeyInput) -> None:
        self._do(plan.key(input))

    def hold_key(self, context: BetaToolsetCallContext, input: BetaComputerHoldKeyInput) -> None:
        self._do(plan.hold_key(input))

    def wait(self, context: BetaToolsetCallContext, input: BetaComputerWaitInput) -> None:
        self._do(plan.wait(input))


class AsyncClaudeComputer(BetaAsyncAbstractComputerToolset20260801):
    """ClaudeComputer for AsyncAnthropic, through an AsyncSandboxes client."""

    def __init__(
        self,
        sandboxes: AsyncSandboxes,
        sandbox_id: str,
        *,
        confirm: BetaAsyncComputerConfirmCallable | None,
        configs: BetaComputerToolsetConfigsParam | None = None,
        tool_configs: BetaToolConfigs | None = None,
    ) -> None:
        super().__init__(configs=configs, confirm=confirm, tool_configs=tool_configs)
        self._sandboxes = sandboxes
        self._sandbox_id = sandbox_id

    async def _do(self, call: DesktopCall) -> ControlDesktopResponse:
        try:
            answer = await self._sandboxes.control_desktop(
                self._sandbox_id, actions=call.actions, skip_screenshot=not call.image, screenshot_region=call.region
            )
            return check(answer, call)
        except SandboxesError as error:
            raise ToolError(error.message or type(error).__name__) from None
        except DesktopRefusedError as error:
            raise ToolError(error.message) from None

    async def screenshot(
        self, context: BetaToolsetCallContext, input: BetaComputerScreenshotInput
    ) -> BetaScreenshotResult:
        return screenshot_result(await self._do(plan.screenshot()))

    async def zoom(self, context: BetaToolsetCallContext, input: BetaComputerZoomInput) -> BetaScreenshotResult:
        return screenshot_result(await self._do(plan.zoom(input)))

    async def cursor_position(
        self, context: BetaToolsetCallContext, input: BetaComputerCursorPositionInput
    ) -> BetaComputerCursorPositionResult:
        return cursor_result(await self._do(plan.cursor_position()))

    async def left_click(self, context: BetaToolsetCallContext, input: BetaComputerLeftClickInput) -> None:
        await self._do(plan.click(input, LEFT, 1))

    async def right_click(self, context: BetaToolsetCallContext, input: BetaComputerRightClickInput) -> None:
        await self._do(plan.click(input, RIGHT, 1))

    async def middle_click(self, context: BetaToolsetCallContext, input: BetaComputerMiddleClickInput) -> None:
        await self._do(plan.click(input, MIDDLE, 1))

    async def double_click(self, context: BetaToolsetCallContext, input: BetaComputerDoubleClickInput) -> None:
        await self._do(plan.click(input, LEFT, 2))

    async def triple_click(self, context: BetaToolsetCallContext, input: BetaComputerTripleClickInput) -> None:
        await self._do(plan.click(input, LEFT, 3))

    async def left_click_drag(self, context: BetaToolsetCallContext, input: BetaComputerLeftClickDragInput) -> None:
        await self._do(plan.left_click_drag(input))

    async def mouse_move(self, context: BetaToolsetCallContext, input: BetaComputerMouseMoveInput) -> None:
        await self._do(plan.mouse_move(input))

    async def left_mouse_down(self, context: BetaToolsetCallContext, input: BetaComputerLeftMouseDownInput) -> None:
        await self._do(plan.left_mouse_down())

    async def left_mouse_up(self, context: BetaToolsetCallContext, input: BetaComputerLeftMouseUpInput) -> None:
        await self._do(plan.left_mouse_up())

    async def scroll(self, context: BetaToolsetCallContext, input: BetaComputerScrollInput) -> None:
        await self._do(plan.scroll(input))

    async def type(self, context: BetaToolsetCallContext, input: BetaComputerTypeInput) -> None:
        await self._do(plan.type_text(input))

    async def key(self, context: BetaToolsetCallContext, input: BetaComputerKeyInput) -> None:
        await self._do(plan.key(input))

    async def hold_key(self, context: BetaToolsetCallContext, input: BetaComputerHoldKeyInput) -> None:
        await self._do(plan.hold_key(input))

    async def wait(self, context: BetaToolsetCallContext, input: BetaComputerWaitInput) -> None:
        await self._do(plan.wait(input))


MediaType = Literal["image/png", "image/jpeg", "image/gif", "image/webp"]
MEDIA_TYPES: dict[str, MediaType] = {
    "image/png": "image/png",
    "image/jpeg": "image/jpeg",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}
"""The image types a toolset's image block carries, by the name Screenshot.mime_type gives."""


def screenshot_result(answer: ControlDesktopResponse) -> BetaScreenshotResult:
    try:
        shot = image(answer)
    except DesktopRefusedError as error:
        raise ToolError(error.message) from None

    media_type = MEDIA_TYPES.get(shot.mime_type)
    if media_type is None:
        raise ToolError("The desktop answered with an image of a type Claude does not read.")
    return BetaScreenshotResult(data=base64_image(shot), media_type=media_type)


def cursor_result(answer: ControlDesktopResponse) -> BetaComputerCursorPositionResult:
    shot = answer.screenshot
    if shot is None:
        raise ToolError("The desktop answered without the pointer's position.")
    return BetaComputerCursorPositionResult(x=shot.cursor_x, y=shot.cursor_y)
