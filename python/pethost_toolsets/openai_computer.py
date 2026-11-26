"""OpenAI's computer use on a sandbox's desktop: drivers of the openai SDK's ComputerToolset,
OpenAIComputer for it and AsyncOpenAIComputer for AsyncComputerToolset. Every action is one
ControlDesktop call (_openai_computer_plan), and the screenshot after a batch of them is the
whole screen, unscaled, so the model's coordinates are the screen's pixels. An action the desktop
refuses raises DesktopRefusedError, which ends the run: the computer tool answers the model with
a screenshot alone, and has no way to tell it why."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from openai.lib.computer import AsyncComputerDriver, ComputerDriver, Screenshot
from openai.types.responses import computer_action as modern
from openai.types.responses import response_computer_tool_call as legacy
from pethost.sandboxes import AsyncSandboxes, ControlDesktopResponse, Sandboxes

from . import _openai_computer_plan as plan
from ._desktop import DesktopCall, base64_image, check, image


class Point(Protocol):
    @property
    def x(self) -> int: ...

    @property
    def y(self) -> int: ...


def points(path: Sequence[Point]) -> list[tuple[int, int]]:
    return [(point.x, point.y) for point in path]


def computer_screenshot(answer: ControlDesktopResponse) -> Screenshot:
    shot = image(answer)
    return {"type": "computer_screenshot", "image_url": f"data:{shot.mime_type};base64,{base64_image(shot)}"}


class OpenAIComputer(ComputerDriver):
    """The desktop of one sandbox, through a Sandboxes client: `ComputerToolset(OpenAIComputer(...))`.
    It holds nothing to close: the sandbox's desktop runs on after the run."""

    def __init__(self, sandboxes: Sandboxes, sandbox_id: str) -> None:
        self._sandboxes = sandboxes
        self._sandbox_id = sandbox_id

    def _do(self, call: DesktopCall) -> ControlDesktopResponse:
        answer = self._sandboxes.control_desktop(
            self._sandbox_id, actions=call.actions, skip_screenshot=not call.image, screenshot_region=call.region
        )
        return check(answer, call)

    def screenshot(self) -> Screenshot:
        return computer_screenshot(self._do(plan.screenshot()))

    def click(self, action: modern.Click | legacy.ActionClick) -> None:
        self._do(plan.click(action.x, action.y, action.button, action.keys))

    def double_click(self, action: modern.DoubleClick | legacy.ActionDoubleClick) -> None:
        self._do(plan.double_click(action.x, action.y, action.keys))

    def drag(self, action: modern.Drag | legacy.ActionDrag) -> None:
        self._do(plan.drag(points(action.path), action.keys))

    def keypress(self, action: modern.Keypress | legacy.ActionKeypress) -> None:
        self._do(plan.keypress(action.keys))

    def move(self, action: modern.Move | legacy.ActionMove) -> None:
        self._do(plan.move(action.x, action.y, action.keys))

    def scroll(self, action: modern.Scroll | legacy.ActionScroll) -> None:
        self._do(plan.scroll(action.x, action.y, action.scroll_x, action.scroll_y, action.keys))

    def type(self, action: modern.Type | legacy.ActionType) -> None:
        self._do(plan.type_text(action.text))

    def wait(self, action: modern.Wait | legacy.ActionWait) -> None:
        self._do(plan.wait())


class AsyncOpenAIComputer(AsyncComputerDriver):
    """OpenAIComputer for AsyncComputerToolset, through an AsyncSandboxes client."""

    def __init__(self, sandboxes: AsyncSandboxes, sandbox_id: str) -> None:
        self._sandboxes = sandboxes
        self._sandbox_id = sandbox_id

    async def _do(self, call: DesktopCall) -> ControlDesktopResponse:
        answer = await self._sandboxes.control_desktop(
            self._sandbox_id, actions=call.actions, skip_screenshot=not call.image, screenshot_region=call.region
        )
        return check(answer, call)

    async def screenshot(self) -> Screenshot:
        return computer_screenshot(await self._do(plan.screenshot()))

    async def click(self, action: modern.Click | legacy.ActionClick) -> None:
        await self._do(plan.click(action.x, action.y, action.button, action.keys))

    async def double_click(self, action: modern.DoubleClick | legacy.ActionDoubleClick) -> None:
        await self._do(plan.double_click(action.x, action.y, action.keys))

    async def drag(self, action: modern.Drag | legacy.ActionDrag) -> None:
        await self._do(plan.drag(points(action.path), action.keys))

    async def keypress(self, action: modern.Keypress | legacy.ActionKeypress) -> None:
        await self._do(plan.keypress(action.keys))

    async def move(self, action: modern.Move | legacy.ActionMove) -> None:
        await self._do(plan.move(action.x, action.y, action.keys))

    async def scroll(self, action: modern.Scroll | legacy.ActionScroll) -> None:
        await self._do(plan.scroll(action.x, action.y, action.scroll_x, action.scroll_y, action.keys))

    async def type(self, action: modern.Type | legacy.ActionType) -> None:
        await self._do(plan.type_text(action.text))

    async def wait(self, action: modern.Wait | legacy.ActionWait) -> None:
        await self._do(plan.wait())
