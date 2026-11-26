"""OpenAI's computer use by code on a sandbox: the function tools exec_py and exec_js, which OpenAI's
guide recommends for GPT-6 Astra, run in the sandbox's code runtime (pethost-code). OpenAICode is
for ResponsesToolRunner, AsyncOpenAICode for AsyncResponsesToolRunner: `functions=code.functions`.

Python drives the desktop with PyAutoGUI, JavaScript the desktop's Chrome with Playwright, and each
is a session of the runtime that keeps its variables from one call to the next, until close()
stops them or the sandbox stops (a pause keeps them). A call is one RunCommand, with a GetCommand
for each 45 s more the code takes, and a ReadFile for each image it displayed. Its output is what
the code printed, logged or displayed, its error's traceback, or the runtime's words when it could
not run the code; a sandbox the API refuses raises SandboxesError, which ends the run."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self

from openai.lib.responses_tool_runner import AsyncRegisteredFunction, RegisteredFunction
from openai.types.responses.response_function_call_output_item_list_param import (
    ResponseFunctionCallOutputItemListParam,
    ResponseFunctionCallOutputItemParam,
)
from pethost.sandboxes import AsyncSandboxes, Command, CommandState, Sandboxes, SandboxesError

from . import _code_runtime as runtime

class OpenAICode:
    """exec_py and exec_js on one sandbox, through a Sandboxes client.

    `session` names the runtime's sessions (one a language), so that another OpenAICode, or a later
    run, takes up their variables; absent, a new name. `timeout_seconds` is how long one call's code
    may run, 600 at most.
    """

    def __init__(
        self,
        sandboxes: Sandboxes,
        sandbox_id: str,
        *,
        session: str | None = None,
        timeout_seconds: float = runtime.TIMEOUT_SECONDS,
    ) -> None:
        self._sandboxes = sandboxes
        self._sandbox_id = sandbox_id
        self.session = session or runtime.new_session()
        self._timeout = runtime.checked_timeout(timeout_seconds)

    @property
    def functions(self) -> list[RegisteredFunction]:
        return [RegisteredFunction(runtime.tool(name), self._executor(name)) for name in runtime.TOOLS]

    def _executor(self, name: str) -> Callable[[dict[str, object]], ResponseFunctionCallOutputItemListParam]:
        language, _ = runtime.TOOLS[name]
        return lambda arguments: self.run(language, runtime.code_of(arguments))

    def run(self, language: runtime.Language, code: str) -> ResponseFunctionCallOutputItemListParam:
        """Runs the code in the language's session, and answers the tool's output."""
        started = self._sandboxes.run_command(
            self._sandbox_id,
            command=runtime.command(language, self.session, self._timeout),
            stdin=code,
            wait_seconds=runtime.WAIT_SECONDS,
        )
        result = runtime.answer(self._finish(started))
        items: list[ResponseFunctionCallOutputItemParam] = []
        budget = runtime.IMAGE_BUDGET_BYTES
        images = 0
        for kind, value in result.items:
            if kind == "text":
                items.append(runtime.text_item(value))
                continue
            images += 1
            if images > runtime.IMAGES_MAX:
                items.append(runtime.image_left_out(None))
                continue
            item, used = self._image(value, budget)
            budget -= used
            items.append(item)
        return runtime.output(items)

    def _finish(self, command: Command) -> Command:
        for _ in range(runtime.waits(self._timeout)):
            if command.state is not CommandState.RUNNING:
                return command
            command = self._sandboxes.get_command(
                self._sandbox_id, command_id=command.command_id, wait_seconds=runtime.WAIT_SECONDS
            )
        if command.state is CommandState.RUNNING:
            command = self._sandboxes.stop_command(self._sandbox_id, command_id=command.command_id)
        return command

    def _image(self, path: str, budget: int) -> tuple[ResponseFunctionCallOutputItemParam, int]:
        """The image at the path, read a MiB a call, and the bytes it took; a note in its place when
        it would pass the budget."""
        data = bytearray()
        while True:
            try:
                part = self._sandboxes.read_file(
                    self._sandbox_id, path=path, offset_bytes=len(data), length_bytes=runtime.READ_BYTES
                )
            except SandboxesError as error:
                return runtime.image_unread(error.message), 0
            chunk = part.data if part.data is not None else (part.text or "").encode()
            if max(part.size_bytes, len(data) + len(chunk)) > budget:
                return runtime.image_left_out(max(part.size_bytes, len(data) + len(chunk))), 0
            data += chunk
            if not chunk or len(data) >= part.size_bytes:
                break
        if not data.startswith(runtime.PNG):
            return runtime.image_unread("it is not a PNG."), 0
        return runtime.image_item(bytes(data)), len(data)

    def close(self) -> None:
        """Stops the sessions, their variables with them. The desktop and Chrome run on."""
        self._sandboxes.run_command(self._sandbox_id, command=runtime.stop_command(self.session))

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()


class AsyncOpenAICode:
    """OpenAICode for AsyncResponsesToolRunner, through an AsyncSandboxes client."""

    def __init__(
        self,
        sandboxes: AsyncSandboxes,
        sandbox_id: str,
        *,
        session: str | None = None,
        timeout_seconds: float = runtime.TIMEOUT_SECONDS,
    ) -> None:
        self._sandboxes = sandboxes
        self._sandbox_id = sandbox_id
        self.session = session or runtime.new_session()
        self._timeout = runtime.checked_timeout(timeout_seconds)

    @property
    def functions(self) -> list[AsyncRegisteredFunction]:
        return [AsyncRegisteredFunction(runtime.tool(name), self._executor(name)) for name in runtime.TOOLS]

    def _executor(self, name: str) -> Callable[[dict[str, object]], Awaitable[ResponseFunctionCallOutputItemListParam]]:
        language, _ = runtime.TOOLS[name]

        async def execute(arguments: dict[str, object]) -> ResponseFunctionCallOutputItemListParam:
            return await self.run(language, runtime.code_of(arguments))

        return execute

    async def run(self, language: runtime.Language, code: str) -> ResponseFunctionCallOutputItemListParam:
        """Runs the code in the language's session, and answers the tool's output."""
        started = await self._sandboxes.run_command(
            self._sandbox_id,
            command=runtime.command(language, self.session, self._timeout),
            stdin=code,
            wait_seconds=runtime.WAIT_SECONDS,
        )
        result = runtime.answer(await self._finish(started))
        items: list[ResponseFunctionCallOutputItemParam] = []
        budget = runtime.IMAGE_BUDGET_BYTES
        images = 0
        for kind, value in result.items:
            if kind == "text":
                items.append(runtime.text_item(value))
                continue
            images += 1
            if images > runtime.IMAGES_MAX:
                items.append(runtime.image_left_out(None))
                continue
            item, used = await self._image(value, budget)
            budget -= used
            items.append(item)
        return runtime.output(items)

    async def _finish(self, command: Command) -> Command:
        for _ in range(runtime.waits(self._timeout)):
            if command.state is not CommandState.RUNNING:
                return command
            command = await self._sandboxes.get_command(
                self._sandbox_id, command_id=command.command_id, wait_seconds=runtime.WAIT_SECONDS
            )
        if command.state is CommandState.RUNNING:
            command = await self._sandboxes.stop_command(self._sandbox_id, command_id=command.command_id)
        return command

    async def _image(self, path: str, budget: int) -> tuple[ResponseFunctionCallOutputItemParam, int]:
        """The image at the path, read a MiB a call, and the bytes it took; a note in its place when
        it would pass the budget."""
        data = bytearray()
        while True:
            try:
                part = await self._sandboxes.read_file(
                    self._sandbox_id, path=path, offset_bytes=len(data), length_bytes=runtime.READ_BYTES
                )
            except SandboxesError as error:
                return runtime.image_unread(error.message), 0
            chunk = part.data if part.data is not None else (part.text or "").encode()
            if max(part.size_bytes, len(data) + len(chunk)) > budget:
                return runtime.image_left_out(max(part.size_bytes, len(data) + len(chunk))), 0
            data += chunk
            if not chunk or len(data) >= part.size_bytes:
                break
        if not data.startswith(runtime.PNG):
            return runtime.image_unread("it is not a PNG."), 0
        return runtime.image_item(bytes(data)), len(data)

    async def close(self) -> None:
        """Stops the sessions, their variables with them. The desktop and Chrome run on."""
        await self._sandboxes.run_command(self._sandbox_id, command=runtime.stop_command(self.session))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        await self.close()
