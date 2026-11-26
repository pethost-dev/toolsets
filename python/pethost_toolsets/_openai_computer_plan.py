"""The Responses API's computer actions, as the openai SDK's ComputerToolset hands them to a
driver, as ControlDesktop calls: one call each, without an image but for screenshot. Key names go
to the desktop as OpenAI writes them, joined by "+": the desktop reads them ("CTRL", "ENTER",
"ARROWLEFT", "PAGEUP", "CMD"), so no table of them is kept here."""

from __future__ import annotations

from collections.abc import Sequence

from pethost.sandboxes import Click, DesktopAction, Drag, MouseButton, Point, Scroll

from ._desktop import DesktopCall

BUTTONS = {
    "left": MouseButton.LEFT,
    "right": MouseButton.RIGHT,
    "wheel": MouseButton.MIDDLE,
    "back": MouseButton.BACK,
    "forward": MouseButton.FORWARD,
}
"""OpenAI's button names: the wheel is the middle button."""

WAIT_MS = 1000
"""How long the model's wait is: it names no length."""

SCROLL_PX_PER_CLICK = 100
"""Pixels of OpenAI's scroll_x and scroll_y that make one wheel click, as OpenAI's own harness
counts them."""


def screenshot() -> DesktopCall:
    return DesktopCall(image=True)


def click(x: int, y: int, button: str, keys: Sequence[str] | None) -> DesktopCall:
    which = BUTTONS.get(button)
    if which is None:
        raise ValueError(f"No mouse button is named {button!r}.")
    return one(DesktopAction(click=Click(x=x, y=y, button=which, hold_keys=chord(keys))))


def double_click(x: int, y: int, keys: Sequence[str] | None) -> DesktopCall:
    return one(DesktopAction(click=Click(x=x, y=y, button=MouseButton.LEFT, count=2, hold_keys=chord(keys))))


def scroll(x: int, y: int, scroll_x: int, scroll_y: int, keys: Sequence[str] | None) -> DesktopCall:
    action = Scroll(x=x, y=y, down=wheel_clicks(scroll_y), right=wheel_clicks(scroll_x), hold_keys=chord(keys))
    return one(DesktopAction(scroll=action))


def type_text(text: str) -> DesktopCall:
    return one(DesktopAction(type_text=text))


def wait() -> DesktopCall:
    return one(DesktopAction(wait_ms=WAIT_MS))


def move(x: int, y: int, keys: Sequence[str] | None) -> DesktopCall:
    if keys:
        raise ValueError("The desktop moves the pointer with no keys held: it has no such action.")
    return one(DesktopAction(move_mouse=Point(x=x, y=y)))


def keypress(keys: Sequence[str]) -> DesktopCall:
    return one(DesktopAction(press_keys=chord(keys)))


def drag(path: Sequence[tuple[int, int]], keys: Sequence[str] | None) -> DesktopCall:
    points = [Point(x=x, y=y) for x, y in path]
    return one(DesktopAction(drag=Drag(path=points, hold_keys=chord(keys))))


def chord(keys: Sequence[str] | None) -> str:
    """OpenAI's keys pressed together, as press_keys and hold_keys read them. With other keys a
    letter is the key, not its capital: OpenAI's ["CTRL", "A"] is ctrl+a, where the desktop reads
    a lone "A" as the character, shift and all."""
    names = list(keys or ())
    if len(names) > 1:
        names = [name.lower() if len(name) == 1 and name.isascii() and name.isalpha() else name for name in names]
    return "+".join(names)


def wheel_clicks(pixels: int) -> int:
    """OpenAI's scroll distance in wheel clicks: about 100 pixels each, and one at least when it
    is not nothing."""
    if pixels == 0:
        return 0
    clicks = max(1, round(abs(pixels) / SCROLL_PX_PER_CLICK))
    return clicks if pixels > 0 else -clicks


def one(action: DesktopAction) -> DesktopCall:
    return DesktopCall(actions=(action,))
