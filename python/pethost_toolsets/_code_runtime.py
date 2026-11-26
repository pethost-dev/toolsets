"""What the drivers of OpenAI's computer use by code share, sync and async: the two function tools,
exec_py and exec_js, and how a call of one becomes a run of the sandbox's code runtime
(pethost-code, in our base) through RunCommand, and its answer the tool's output. The runtime
keeps each session's variables between runs; a run answers one JSON document on stdout, its
images PNG files the drivers read with ReadFile."""

from __future__ import annotations

import base64
import json
import math
import secrets
import shlex
from dataclasses import dataclass
from typing import Literal

from openai.types.responses import FunctionToolParam
from openai.types.responses.response_function_call_output_item_list_param import (
    ResponseFunctionCallOutputItemListParam,
    ResponseFunctionCallOutputItemParam,
)
from openai.types.responses.response_input_image_content_param import ResponseInputImageContentParam
from openai.types.responses.response_input_text_content_param import ResponseInputTextContentParam
from pethost.sandboxes import Command, CommandState

Language = Literal["python", "javascript"]

TIMEOUT_SECONDS = 120
TIMEOUT_MAX_SECONDS = 600
"""How long a run's code has by default, and at most, as the runtime takes it: a computer-use step is
seconds long."""

WAIT_SECONDS = 45
"""The longest wait of one RunCommand or GetCommand: the API's."""

START_SECONDS = 120
FINISH_GRACE_SECONDS = 30
"""What a run may take beside its code's timeout: the runtime's start of a session (the desktop and
Chrome first, on a first run), and its own grace and the calls' after the code."""

PNG = b"\x89PNG\r\n\x1a\n"

READ_BYTES = 1 << 20
"""The most of a file one ReadFile answers."""

IMAGES_MAX = 16
IMAGE_BUDGET_BYTES = 32 << 20
"""What the images of one call may come to, in number and bytes: the runtime writes PNGs of the
screen, a few hundred KiB each, and what the sandbox names past these is not read, since the
sandbox's answer is the caller's memory to bound."""

TOOLS: dict[str, tuple[Language, str]] = {
    "exec_py": (
        "python",
        "Run Python in a persistent session on the sandbox's Linux desktop (X11), whose globals the next "
        "call still has. Ready without imports: pyautogui, to look at and drive the screen (its fail-safe "
        "is on: the pointer in a corner of the screen stops the code), time, Image (Pillow), log(*values), "
        "which reports text, and display(image), which shows you a Pillow image: "
        "display(pyautogui.screenshot()) shows the screen. What the code prints is reported too, and an "
        "error's traceback.",
    ),
    "exec_js": (
        "javascript",
        "Run JavaScript (Node.js; await works at the top level) in a persistent session with Playwright "
        "attached to the Chrome on the sandbox's desktop. Globals: browser, context (the browser's tabs) "
        "and page (the tab in use; set it to another to switch), log(...values), which reports text, as "
        "console.log does, and display(png), which shows you a PNG image: "
        'display(await page.screenshot()) shows the page. Keep what a later call '
        "needs on globalThis: other variables last one call.",
    ),
}
"""Each tool's language and what the model is told of it."""


def checked_timeout(seconds: float) -> float:
    if not 0 < seconds <= TIMEOUT_MAX_SECONDS:
        raise ValueError(f"timeout_seconds is more than 0 and {TIMEOUT_MAX_SECONDS} at most: {seconds}")
    return seconds


def waits(timeout_seconds: float) -> int:
    """How many waits of WAIT_SECONDS a run may take, its session's start among them."""
    return math.ceil((START_SECONDS + timeout_seconds + FINISH_GRACE_SECONDS) / WAIT_SECONDS)


def new_session() -> str:
    """A session of its own for a driver: two drivers on one sandbox keep apart."""
    return "openai-" + secrets.token_hex(4)


def tool(name: str) -> FunctionToolParam:
    _, description = TOOLS[name]
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "The code to run."}},
            "required": ["code"],
            "additionalProperties": False,
        },
    }


def command(language: Language, session: str, timeout_seconds: float) -> str:
    """The run's command line; each value joined to its option, so that none reads as an option."""
    return shlex.join(
        ["pethost-code", "run", f"--session={session}", f"--language={language}", f"--timeout={timeout_seconds:g}"]
    )


def stop_command(session: str) -> str:
    return shlex.join(["pethost-code", "stop", f"--session={session}"])


def code_of(arguments: dict[str, object]) -> str:
    code = arguments.get("code")
    if not isinstance(code, str):
        raise ValueError("A call of exec_py or exec_js holds its code as the string `code`.")
    return code


@dataclass(frozen=True)
class Answer:
    """A run's answer: the texts and the images' paths in the sandbox, in their order, as
    ("text", text) and ("image", path)."""

    items: list[tuple[Literal["text", "image"], str]]


def answer(ended: Command) -> Answer:
    """The run's answer from its command: the runtime's own document when it ran the code, and its
    words, or the command's end, when it did not."""
    if ended.state is CommandState.EXITED and ended.exit_code == 0:
        try:
            return Answer(document(ended.stdout))
        except (ValueError, KeyError, TypeError):
            return Answer([("text", "The runtime's answer could not be read.")])
    return Answer([("text", failure(ended))])


def document(stdout: str) -> list[tuple[Literal["text", "image"], str]]:
    """The runtime's JSON document, its last line: a login shell's own words may come before it.
    Lines are split at "\n" alone, which JSON escapes in a string; other line breaks Python knows,
    U+2028 among them, may stand in a text as they are."""
    lines = stdout.strip("\n").split("\n")
    items: list[tuple[Literal["text", "image"], str]] = []
    for item in json.loads(lines[-1])["output"]:
        if item["type"] == "image":
            items.append(("image", str(item["path"])))
        else:
            items.append(("text", str(item["text"])))
    return items


def failure(ended: Command) -> str:
    words = ended.stderr.strip()
    if ended.state is CommandState.EXITED and words:
        return f"The code did not run: {words}"
    if ended.state is CommandState.LOST:
        return "The run's end is not known: the sandbox lost its memory while it ran. Its session's variables are gone."
    return f"The run ended without an answer ({ended.state.name}, exit code {ended.exit_code}). {words}".strip()


def text_item(text: str) -> ResponseInputTextContentParam:
    return {"type": "input_text", "text": text}


def image_item(png: bytes) -> ResponseInputImageContentParam:
    """An image at its own size: OpenAI's guide asks for detail "original" in computer use."""
    url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return {"type": "input_image", "image_url": url, "detail": "original"}


def image_unread(why: str) -> ResponseInputTextContentParam:
    """What stands for an image the code displayed that could not be shown: its file gone or not a PNG."""
    return text_item(f"[An image the code displayed was left out: {why}]")


def image_left_out(size: int | None) -> ResponseInputTextContentParam:
    """What stands for an image the call's budget has no room for."""
    if size is None:
        return text_item(f"[An image was left out: a call shows {IMAGES_MAX} at most.]")
    return text_item(f"[An image of {size} bytes was left out: a call's images take {IMAGE_BUDGET_BYTES >> 20} MiB at most.]")


def output(items: list[ResponseFunctionCallOutputItemParam]) -> ResponseFunctionCallOutputItemListParam:
    """The tool's output, which says so when the code wrote nothing: an empty output reads as a
    failure to a model."""
    return items or [text_item("The code ran and wrote nothing.")]
