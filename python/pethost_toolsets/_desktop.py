"""What the drivers over a sandbox's screen share: one call of theirs is one ControlDesktop call,
and the server judges it. They check nothing it checks (a key's name, a point on the screen):
they send, and pass on its refusal."""

from __future__ import annotations

import base64
from dataclasses import dataclass

from pethost.sandboxes import ControlDesktopResponse, DesktopAction, DesktopFailure, ScreenRegion, Screenshot


@dataclass(frozen=True)
class DesktopCall:
    """One ControlDesktop call: the actions in order, and whether its answer carries an image (of
    the whole screen, or of `region`)."""

    actions: tuple[DesktopAction, ...] = ()
    image: bool = False
    region: ScreenRegion | None = None


class DesktopRefusedError(Exception):
    """The desktop did not do every action of a call: `done_count` of them were done, and the next
    failed for `failure` (to branch on), as `message` says (prose)."""

    def __init__(self, message: str, failure: DesktopFailure, done_count: int) -> None:
        super().__init__(message)
        self.message = message
        self.failure = failure
        self.done_count = done_count


def check(answer: ControlDesktopResponse, call: DesktopCall) -> ControlDesktopResponse:
    """The answer, when the desktop did every action; else DesktopRefusedError with its words."""
    if answer.failure is DesktopFailure.UNSPECIFIED and answer.done_count >= len(call.actions):
        return answer

    message = answer.failure_message or "The desktop did not do every action, and gave no reason."
    raise DesktopRefusedError(message, answer.failure, answer.done_count)


def image(answer: ControlDesktopResponse) -> Screenshot:
    """The answer's screenshot, which a call that asked for an image holds."""
    shot = answer.screenshot
    if shot is None or not shot.image:
        raise DesktopRefusedError("The desktop answered without an image.", DesktopFailure.UNSPECIFIED, 0)
    return shot


def base64_image(shot: Screenshot) -> str:
    return base64.b64encode(shot.image).decode("ascii")

