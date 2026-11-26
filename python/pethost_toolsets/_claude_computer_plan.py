"""The computer toolset's members (computer_toolset_20260801) as ControlDesktop calls: one call each,
without an image but for screenshot and zoom. Claude's coordinates are the screen's pixels, since
its screenshots are the whole screen unscaled (1280x800 fits every current model's image limits),
and a zoom's region is in those pixels too."""

from __future__ import annotations

from typing import Protocol

from anthropic.tools import ToolError
from anthropic.types.beta import (
    BetaComputerHoldKeyInput,
    BetaComputerKeyInput,
    BetaComputerLeftClickDragInput,
    BetaComputerMouseMoveInput,
    BetaComputerScrollInput,
    BetaComputerTypeInput,
    BetaComputerWaitInput,
    BetaComputerZoomInput,
)
from pethost.sandboxes import (
    Click,
    DesktopAction,
    Drag,
    HoldKeys,
    MouseButton,
    MouseButtonChange,
    Point,
    ScreenRegion,
    Scroll,
)

from ._desktop import DesktopCall

MILLISECONDS_MAX = 0xFFFF_FFFF
"""The most milliseconds a wait or a hold can say: the API carries them as unsigned 32-bit numbers."""

SCROLL_SIGNS: dict[str, tuple[int, int]] = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
"""Each scroll direction as the signs of Scroll's down and right."""


class ClickInput(Protocol):
    """What every click member takes: where (absent = where the pointer is) and the keys held."""

    @property
    def coordinate(self) -> list[int] | None: ...

    @property
    def text(self) -> str | None: ...


def screenshot() -> DesktopCall:
    return DesktopCall(image=True)


def zoom(input: BetaComputerZoomInput) -> DesktopCall:
    x0, y0, x1, y1 = numbers(input.region, 4, "region: four numbers, [x0, y0, x1, y1]")
    return DesktopCall(image=True, region=ScreenRegion(x=x0, y=y0, width=x1 - x0, height=y1 - y0))


def cursor_position() -> DesktopCall:
    return DesktopCall()


def click(input: ClickInput, button: MouseButton, count: int) -> DesktopCall:
    held = input.text or ""
    if input.coordinate is None:
        action = Click(at_pointer=True, button=button, count=count, hold_keys=held)
    else:
        at = point(input.coordinate, "coordinate")
        action = Click(x=at.x, y=at.y, button=button, count=count, hold_keys=held)
    return one(DesktopAction(click=action))


def left_click_drag(input: BetaComputerLeftClickDragInput) -> DesktopCall:
    path = [point(input.start_coordinate, "start_coordinate"), point(input.coordinate, "coordinate")]
    return one(DesktopAction(drag=Drag(path=path, hold_keys=input.text or "")))


def mouse_move(input: BetaComputerMouseMoveInput) -> DesktopCall:
    return one(DesktopAction(move_mouse=point(input.coordinate, "coordinate")))


def left_mouse_down() -> DesktopCall:
    return one(DesktopAction(mouse_down=MouseButtonChange(button=MouseButton.LEFT)))


def left_mouse_up() -> DesktopCall:
    return one(DesktopAction(mouse_up=MouseButtonChange(button=MouseButton.LEFT)))


def scroll(input: BetaComputerScrollInput) -> DesktopCall:
    amount = input.scroll_amount
    # The sign of a wheel action is its direction: a negative amount would scroll against the one named.
    if amount < 0:
        raise ToolError("scroll_amount: wheel clicks, 0 or more")
    signs = SCROLL_SIGNS.get(input.scroll_direction)
    if signs is None:
        raise ToolError("scroll_direction: up, down, left or right")
    down, right = signs[0] * amount, signs[1] * amount
    held = input.text or ""
    if input.coordinate is None:
        action = Scroll(at_pointer=True, down=down, right=right, hold_keys=held)
    else:
        at = point(input.coordinate, "coordinate")
        action = Scroll(x=at.x, y=at.y, down=down, right=right, hold_keys=held)
    return one(DesktopAction(scroll=action))


def type_text(input: BetaComputerTypeInput) -> DesktopCall:
    return one(DesktopAction(type_text=input.text))


# REQUEST_MAX is what a request of the runtime API may hold (SandboxRuntimeService's bounds): keys
# repeated past it could never be sent, and building them could take this process's memory.
REQUEST_MAX = 1 << 20


def key(input: BetaComputerKeyInput) -> DesktopCall:
    # press_keys reads chords apart by spaces one after the other: a repeat is the chord again.
    repeat = 1 if input.repeat is None else input.repeat
    if repeat < 1:
        raise ToolError("repeat: must be 1 or more")
    if (len(input.text) + 1) * repeat > REQUEST_MAX:
        raise ToolError("repeat: the keys repeated are more than one call carries")
    return one(DesktopAction(press_keys=" ".join([input.text] * repeat)))


def hold_key(input: BetaComputerHoldKeyInput) -> DesktopCall:
    return one(DesktopAction(hold_keys=HoldKeys(keys=input.text, duration_ms=milliseconds(input.duration))))


def wait(input: BetaComputerWaitInput) -> DesktopCall:
    return one(DesktopAction(wait_ms=milliseconds(input.duration)))


def milliseconds(seconds: int) -> int:
    """The model's seconds as milliseconds: a duration the API's field cannot carry (negative, or of
    years) cannot be sent. How long a wait or a hold may be is the desktop's to judge."""
    ms = seconds * 1000
    if not 0 <= ms <= MILLISECONDS_MAX:
        raise ToolError(f"duration: a number of seconds, from 0 to {MILLISECONDS_MAX // 1000}")
    return ms


def one(action: DesktopAction) -> DesktopCall:
    return DesktopCall(actions=(action,))


def point(coordinate: list[int], field: str) -> Point:
    """A point of the model's, in the screen's pixels."""
    x, y = numbers(coordinate, 2, f"{field}: two numbers, [x, y]")
    return Point(x=x, y=y)


def numbers(values: list[int], length: int, expected: str) -> list[int]:
    """The model's list of `length` numbers. Its shape is checked, not its values: a value the
    screen does not have is the desktop's to refuse."""
    if len(values) != length:
        raise ToolError(expected)
    return values
