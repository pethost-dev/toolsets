"""read_page's text, from Playwright's accessibility snapshot of the whole page in its "ai" mode:
YAML-like lines, two spaces a level, each element with its ref ([ref=e5], [ref=f1e2] in a frame)
and its box in the viewport ([box=x,y,width,height]).

The snapshot is always of the whole page, since Playwright resolves a ref against the latest
snapshot of its frame: reading a part by itself would leave the refs read before it unknown. The
part, the depth and the filter are cut from it here."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ._browser_shared import PageRefusal

TEXT_MAX = 50_000
"""The longest text a reading member returns: read_page's documented cap."""

DEPTH_DEFAULT = 15

BOX = re.compile(r" \[box=(-?[\d.]+),(-?[\d.]+),([\d.]+),([\d.]+)\]")
ITEM = re.compile(r"( *)- (/?[A-Za-z]+)")

Box = tuple[float, float, float, float]
"""An element's box in the viewport: x, y, width and height."""

INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "searchbox",
        "checkbox",
        "radio",
        "combobox",
        "listbox",
        "option",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "tab",
        "switch",
        "slider",
        "spinbutton",
        "treeitem",
    }
)
"""The roles a person acts on. An element of another role whose pointer is a hand
([cursor=pointer]) counts too."""


@dataclass(frozen=True)
class Line:
    text: str
    level: int
    role: str

    @property
    def is_property(self) -> bool:
        """A property of the element above it, such as a link's "/url"."""
        return self.role.startswith("/")


def read_page(
    snapshot: str, *, width: float, height: float, filter: str | None, depth: int | None, ref: str | None
) -> str:
    if depth is not None and depth < 0:
        raise PageRefusal("depth: a whole number, 0 or more")
    every = parse(snapshot)
    lines = every if filter == "all" else on_screen(every, width, height)
    if ref is not None:
        if find(every, ref) is None:
            raise PageRefusal(f"No element of this page has the ref {ref!r}: read_page again for the refs it has now.")
        if find(lines, ref) is None:
            return f'The element {ref} is out of the viewport: scroll_to it, or read it with filter "all".'
        lines = subtree(lines, ref)
    lines = within_depth(lines, DEPTH_DEFAULT if depth is None else depth)
    if filter == "interactive":
        lines = interactive(lines)
    return bounded("\n".join(BOX.sub("", line.text) for line in lines), "read a part with ref, or less depth")


def parse(snapshot: str) -> list[Line]:
    lines: list[Line] = []
    for text in snapshot.splitlines():
        item = ITEM.match(text)
        if item is None:  # the rest of a value that runs over lines
            level = (len(text) - len(text.lstrip(" "))) // 2
            lines.append(Line(text, level, ""))
            continue
        lines.append(Line(text, len(item.group(1)) // 2, item.group(2)))
    return lines


def find(lines: list[Line], ref: str) -> int | None:
    """Where the element with this ref is."""
    marker = f"[ref={ref}]"
    return next((i for i, line in enumerate(lines) if marker in line.text), None)


def subtree(lines: list[Line], ref: str) -> list[Line]:
    """The element with this ref, which the lines hold, and all under it, its level made the top."""
    start = find(lines, ref)
    assert start is not None
    top = lines[start].level
    part = [lines[start]]
    for line in lines[start + 1 :]:
        if line.level <= top:
            break
        part.append(line)
    return [Line(line.text[2 * top :], line.level - top, line.role) for line in part]


def on_screen(lines: list[Line], width: float, height: float) -> list[Line]:
    """The lines of elements that show in the viewport or hold one that does, and those with no box
    of their own. An element out of it and all it holds go together; one that holds an element in
    it stays, as a fixed or absolute child (a dialog, a sticky header) is laid out apart from its
    parent. Inside a frame a box is the frame's own, so only the frame is judged."""
    boxes = [box_of(line) for line in lines]
    seen = shown(lines, boxes, width, height)
    kept: list[Line] = []
    hidden_below: int | None = None
    frame_level: int | None = None
    for line, box, line_seen in zip(lines, boxes, seen):
        if hidden_below is not None and line.level > hidden_below:
            continue
        hidden_below = None
        if frame_level is not None and line.level <= frame_level:
            frame_level = None

        if frame_level is None and box is not None and not line_seen:
            hidden_below = line.level
            continue
        if line.role == "iframe" and frame_level is None:
            frame_level = line.level
        kept.append(line)
    return kept


def shown(lines: list[Line], boxes: list[Box | None], width: float, height: float) -> list[bool]:
    """Whether each line's element shows in the viewport, or holds one that does: what a frame
    holds counts for nothing outside it, its boxes being the frame's own."""
    seen = [box is not None and inside(box, width, height) for box in boxes]
    above = parents(lines)
    for i in reversed(range(len(lines))):  # all an element holds comes after it
        parent = above[i]
        if seen[i] and parent is not None and lines[parent].role != "iframe":
            seen[parent] = True
    return seen


def parents(lines: list[Line]) -> list[int | None]:
    """Where each line's parent is: the nearest line before it of a lower level."""
    found: list[int | None] = []
    open_: list[int] = []
    for i, line in enumerate(lines):
        while open_ and lines[open_[-1]].level >= line.level:
            open_.pop()
        found.append(open_[-1] if open_ else None)
        open_.append(i)
    return found


def box_of(line: Line) -> Box | None:
    """The line's box, when it has one of its own: an element of no size (a closed select's
    options) is where its parent is."""
    box = BOX.search(line.text)
    if box is None:
        return None
    x, y, w, h = (float(group) for group in box.groups())
    return (x, y, w, h) if w > 0 and h > 0 else None


def inside(box: Box, width: float, height: float) -> bool:
    x, y, w, h = box
    return x < width and y < height and x + w > 0 and y + h > 0


def within_depth(lines: list[Line], depth: int) -> list[Line]:
    """The elements down to `depth` levels under the top, with the properties of those kept."""
    kept: list[Line] = []
    for line in lines:
        level = line.level - 1 if line.is_property else line.level
        if level <= depth:
            kept.append(line)
    return kept


def interactive(lines: list[Line]) -> list[Line]:
    """The elements a person acts on, as a flat list, each with its properties under it."""
    kept: list[Line] = []
    owner_level: int | None = None
    for line in lines:
        if line.is_property and owner_level is not None and line.level == owner_level + 1:
            kept.append(Line("  " + line.text.lstrip(" "), 1, line.role))
            continue
        owner_level = None
        if line.role in INTERACTIVE_ROLES or "[cursor=pointer]" in line.text:
            kept.append(Line(line.text.lstrip(" "), 0, line.role))
            owner_level = line.level
    return kept


def bounded(text: str, narrower: str) -> str:
    if len(text) <= TEXT_MAX:
        return text
    return text[:TEXT_MAX] + f"\n[cut at {TEXT_MAX} characters: {narrower}]"
