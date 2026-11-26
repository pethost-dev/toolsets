"""A browser toolset's inputs as Playwright's arguments: key names, held modifiers, addresses,
scroll distances, waits, a zoom's clip and a form field's value. Playwright and the browser
judge the rest: a name not translated here goes to Playwright as written, which refuses one it
does not know. The names a refusal gives the model are Claude's toolset's, whose inputs most of
these are; OpenAI's driver checks its own before it calls one."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from ._browser_shared import PageRefusal

Button = Literal["left", "middle", "right"]
Modifier = Literal["Alt", "Control", "Meta", "Shift"]


KEYS: dict[str, str] = {
    "return": "Enter",
    "enter": "Enter",
    "kp_enter": "Enter",
    "backspace": "Backspace",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "space": "Space",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "page_up": "PageUp",
    "pageup": "PageUp",
    "prior": "PageUp",
    "page_down": "PageDown",
    "pagedown": "PageDown",
    "next": "PageDown",
    "up": "ArrowUp",
    "arrowup": "ArrowUp",
    "down": "ArrowDown",
    "arrowdown": "ArrowDown",
    "left": "ArrowLeft",
    "arrowleft": "ArrowLeft",
    "right": "ArrowRight",
    "arrowright": "ArrowRight",
    "caps_lock": "CapsLock",
    "capslock": "CapsLock",
    "ctrl": "Control",
    "control": "Control",
    "shift": "Shift",
    "alt": "Alt",
    "option": "Alt",
    # The browser is Chrome on Linux, where the shortcuts a Mac's habit presses with cmd (cmd+a,
    # cmd+c, cmd+click) take ctrl. Not "ControlOrMeta": Playwright resolves that by the system the
    # driver runs on, not the browser's. The desktop's own names (keynames.go) make cmd Super,
    # since they press X keys, not Chrome's shortcuts.
    "cmd": "Control",
    "command": "Control",
    "meta": "Meta",
    "super": "Meta",
    "win": "Meta",
    "windows": "Meta",
}
"""Every alias of a key, in lower case, by the names the model writes (xdotool's: "Return",
"BackSpace", "Page_Down"), and the key Playwright calls it; F1 to F24 and single characters need
no entry. The TypeScript driver's table (typescript/src/browser/keys.ts) is the same, entry for
entry: the two packages cannot share a file."""

MODIFIERS: dict[str, Modifier] = {"Alt": "Alt", "Control": "Control", "Meta": "Meta", "Shift": "Shift"}
"""The keys a click holds, as Playwright's click options take them."""

FUNCTION_KEY = re.compile(r"f([1-9]|1[0-9]|2[0-4])")

WHEEL_NOTCH_PX = 100
"""Pixels one notch of the wheel scrolls."""

NOTCHES_MAX = 10
"""The most notches a scroll takes: the browser toolset's range is 1 to 10."""

WHEEL: dict[str, tuple[int, int]] = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
"""Each scroll direction as the signs of the wheel's deltas, right and down positive."""

REPEAT_MAX = 100
"""The most times a key member presses its keys: the browser toolset's range is 1 to 100, and each
press is a round trip to the browser."""

DURATION_MAX_S = 30
"""The longest wait and hold_key the toolset documents."""

LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def playwright_key(name: str) -> str:
    lower = name.lower()
    if lower in KEYS:
        return KEYS[lower]
    if FUNCTION_KEY.fullmatch(lower):
        return lower.upper()
    return name


def chord_keys(chord: str) -> list[str]:
    """The keys of a chord ("ctrl+shift+t", "ctrl++"), each as Playwright names it."""
    if chord == "+":
        return ["+"]
    names = [*chord[:-2].split("+"), "+"] if chord.endswith("++") else chord.split("+")
    if any(not name for name in names):
        raise PageRefusal(f"A key name is missing in {chord!r}.")
    return [playwright_key(name) for name in names]


def key_presses(text: str, repeat: int | None) -> list[list[str]]:
    """Each press of a key member: chords apart by spaces, the whole of them `repeat` times, each
    chord as its keys, which go down in order and up in reverse."""
    times = 1 if repeat is None else repeat
    if not 1 <= times <= REPEAT_MAX:
        raise PageRefusal(f"repeat: a whole number, from 1 to {REPEAT_MAX}")
    chords = [chord_keys(chord) for chord in text.split()]
    if not chords:
        raise PageRefusal("text: name a key")
    return chords * times


def modifiers(text: str | None) -> list[Modifier]:
    """The keys a click holds ("shift", "ctrl+shift", "cmd+alt"); none when absent."""
    if not text:
        return []
    held: list[Modifier] = []
    for name in text.split("+"):
        key = MODIFIERS.get(playwright_key(name.strip()))
        if key is None:
            raise PageRefusal(f"{name!r} is not a modifier key: use shift, ctrl, alt or cmd.")
        held.append(key)
    return held


def milliseconds(seconds: float) -> int:
    if not 0 <= seconds <= DURATION_MAX_S:
        raise PageRefusal(f"duration: must be from 0 to {DURATION_MAX_S} seconds")
    return round(seconds * 1000)


def wheel(direction: str, amount: int | None) -> tuple[float, float]:
    """A scroll as the wheel's deltas, right and down positive: three notches when the model names
    no amount. One out of the toolset's range is refused: a negative one would scroll against the
    direction named."""
    notches = 3 if amount is None else amount
    if not 1 <= notches <= NOTCHES_MAX:
        raise PageRefusal(f"scroll_amount: wheel notches, from 1 to {NOTCHES_MAX}")
    signs = WHEEL.get(direction)
    if signs is None:
        raise PageRefusal("scroll_direction: up, down, left or right")
    px = notches * WHEEL_NOTCH_PX
    return (float(signs[0] * px), float(signs[1] * px))


def address(url: str) -> str:
    """Where a navigate goes: an http or https address, about:blank, or a host with no scheme, which
    opens as https, or as http on the sandbox's own localhost, the way Chrome reads a typed one."""
    if re.search(r"[\s\x00-\x1f\x7f]", url):
        raise PageRefusal("url: the address holds a space or a control character")
    if url == "about:blank":
        return url

    scheme = re.match(r"([a-zA-Z][a-zA-Z0-9+.-]*):(.?)", url)
    # "localhost:3000" is a host and its port, not a scheme.
    if scheme and not scheme.group(2).isdigit():
        if scheme.group(1).lower() in ("http", "https"):
            return url
        raise PageRefusal(f"url: only http and https addresses open here, not {scheme.group(1)}:")

    local = any(url == host or url.startswith((host + ":", host + "/")) for host in LOCAL_HOSTS)
    return ("http://" if local else "https://") + url


def zoom_clip(region: Sequence[int], page_x: float, page_y: float, width: float, height: float) -> dict[str, float]:
    """The clip of Page.captureScreenshot for a zoom: the region of the viewport, in the document's
    coordinates (the viewport's plus where it is scrolled to), drawn as large as fits the viewport."""
    if len(region) != 4:
        raise PageRefusal("region: expected [x0, y0, x1, y1]")
    x0, y0, x1, y1 = region
    if x1 <= x0 or y1 <= y0:
        raise PageRefusal("region: x1 must be greater than x0, and y1 than y0")

    w, h = x1 - x0, y1 - y0
    scale = min(width / w, height / h)
    return {"x": x0 + page_x, "y": y0 + page_y, "width": w, "height": h, "scale": scale}


def form_text(value: str | float | bool) -> str:
    """A form field's value as text: 3 rather than 3.0, true rather than True."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
