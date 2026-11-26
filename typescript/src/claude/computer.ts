/**
 * ClaudeComputer: Claude's computer toolset (computer_toolset_20260801) over the desktop of a
 * Pethost Agent Sandbox. Every member the model calls is one ControlDesktop call; only screenshot
 * and zoom bring an image back. The desktop's screen, 1280×800, fits every current model's image
 * limits, so coordinates are the screen's pixels as they are, after a zoom too.
 *
 * The server judges every action: a point off the screen, a key it does not know, a duration too
 * long. Its refusal reaches the model as the member's error, in its words; nothing here repeats its
 * rules.
 */
import {
  BetaAbstractComputerToolset20260801,
  ToolError,
  type BetaComputerCursorPositionResult,
  type BetaComputerToolsetOptions,
  type BetaScreenshotResult,
  type BetaToolsetCallContext,
} from "@anthropic-ai/sdk/helpers/beta/toolsets";
import type {
  BetaComputerDoubleClickInput,
  BetaComputerHoldKeyInput,
  BetaComputerKeyInput,
  BetaComputerLeftClickDragInput,
  BetaComputerLeftClickInput,
  BetaComputerMiddleClickInput,
  BetaComputerMouseMoveInput,
  BetaComputerRightClickInput,
  BetaComputerScrollInput,
  BetaComputerTripleClickInput,
  BetaComputerTypeInput,
  BetaComputerWaitInput,
  BetaComputerZoomInput,
} from "@anthropic-ai/sdk/resources/beta";
import {
  MouseButton,
  SandboxesError,
  type ControlDesktopRequest,
  type DesktopActionInput,
  type PointInput,
  type Screenshot,
} from "pethost/sandboxes";

import { DesktopRefusedError, act, base64, type Desktop, type DesktopClient } from "../desktop.ts";

type Ctx = BetaToolsetCallContext;
type Pair = [number, number];
type Quad = [number, number, number, number];

/** The most milliseconds a wait or hold can say: the API carries them as unsigned 32-bit numbers. */
const MILLISECONDS_MAX = 0xffff_ffff;

export interface ClaudeComputerOptions extends BetaComputerToolsetOptions {
  /** The client the calls go through: `new Sandboxes({ token })` of `pethost/sandboxes`. */
  sandboxes: DesktopClient;
  /** The sandbox whose desktop the model uses. */
  sandboxId: string;
}

/**
 * The computer toolset over a sandbox's desktop. Pass it in `tools` of the tool runner, or answer
 * each computer `tool_use` with `toolResult`. The SDK asks for `confirm` while `type`, `key` and
 * `hold_key` are on: pass one, or turn them off in `configs`.
 */
export class ClaudeComputer extends BetaAbstractComputerToolset20260801 {
  readonly #desktop: Desktop;

  constructor({ sandboxes, sandboxId, ...options }: ClaudeComputerOptions) {
    super(options);
    this.#desktop = { sandboxes, sandboxId };
  }

  protected override async screenshot(ctx: Ctx): Promise<BetaScreenshotResult> {
    return image(await this.#call(ctx, {}));
  }

  protected override async zoom(ctx: Ctx, input: BetaComputerZoomInput): Promise<BetaScreenshotResult> {
    const [x0, y0, x1, y1] = numbers(input.region, 4, "region: four numbers, [x0, y0, x1, y1]") as Quad;
    const region = { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };
    return image(await this.#call(ctx, { screenshotRegion: region }));
  }

  protected override async left_click(ctx: Ctx, input: BetaComputerLeftClickInput): Promise<void> {
    await this.#click(ctx, input, MouseButton.LEFT, 1);
  }

  protected override async right_click(ctx: Ctx, input: BetaComputerRightClickInput): Promise<void> {
    await this.#click(ctx, input, MouseButton.RIGHT, 1);
  }

  protected override async middle_click(ctx: Ctx, input: BetaComputerMiddleClickInput): Promise<void> {
    await this.#click(ctx, input, MouseButton.MIDDLE, 1);
  }

  protected override async double_click(ctx: Ctx, input: BetaComputerDoubleClickInput): Promise<void> {
    await this.#click(ctx, input, MouseButton.LEFT, 2);
  }

  protected override async triple_click(ctx: Ctx, input: BetaComputerTripleClickInput): Promise<void> {
    await this.#click(ctx, input, MouseButton.LEFT, 3);
  }

  protected override async left_click_drag(ctx: Ctx, input: BetaComputerLeftClickDragInput): Promise<void> {
    const path = [point(input.start_coordinate, "start_coordinate"), point(input.coordinate, "coordinate")];
    await this.#do(ctx, { drag: { path, ...held(input.text) } });
  }

  protected override async mouse_move(ctx: Ctx, input: BetaComputerMouseMoveInput): Promise<void> {
    await this.#do(ctx, { moveMouse: point(input.coordinate, "coordinate") });
  }

  protected override async left_mouse_down(ctx: Ctx): Promise<void> {
    await this.#do(ctx, { mouseDown: { button: MouseButton.LEFT } });
  }

  protected override async left_mouse_up(ctx: Ctx): Promise<void> {
    await this.#do(ctx, { mouseUp: { button: MouseButton.LEFT } });
  }

  protected override async cursor_position(ctx: Ctx): Promise<BetaComputerCursorPositionResult> {
    const shot = await this.#call(ctx, { skipScreenshot: true });
    return { x: shot.cursorX, y: shot.cursorY };
  }

  protected override async scroll(ctx: Ctx, input: BetaComputerScrollInput): Promise<void> {
    const where = input.coordinate == null ? { atPointer: true } : point(input.coordinate, "coordinate");
    await this.#do(ctx, { scroll: { ...wheel(input), ...where, ...held(input.text) } });
  }

  protected override async type_(ctx: Ctx, input: BetaComputerTypeInput): Promise<void> {
    await this.#do(ctx, { typeText: input.text });
  }

  protected override async key(ctx: Ctx, input: BetaComputerKeyInput): Promise<void> {
    await this.#do(ctx, { pressKeys: repeated(input.text, input.repeat ?? 1) });
  }

  protected override async hold_key(ctx: Ctx, input: BetaComputerHoldKeyInput): Promise<void> {
    await this.#do(ctx, { holdKeys: { keys: input.text, durationMs: milliseconds(input.duration) } });
  }

  protected override async wait(ctx: Ctx, input: BetaComputerWaitInput): Promise<void> {
    await this.#do(ctx, { waitMs: milliseconds(input.duration) });
  }

  /** A click where the model said, or where the pointer is when it gave no coordinate. */
  async #click(ctx: Ctx, input: BetaComputerLeftClickInput, button: MouseButton, count: number): Promise<void> {
    const where = input.coordinate == null ? { atPointer: true } : point(input.coordinate, "coordinate");
    await this.#do(ctx, { click: { ...where, button, count, ...held(input.text) } });
  }

  /** One action, which the model looks at only when it asks: no image comes back. */
  async #do(ctx: Ctx, action: DesktopActionInput): Promise<void> {
    await this.#call(ctx, { actions: [action], skipScreenshot: true });
  }

  /** One ControlDesktop call; a refusal, or a call that failed, is the member's error, in the server's words. */
  async #call(ctx: Ctx, request: Omit<ControlDesktopRequest, "sandboxId">): Promise<Screenshot> {
    try {
      return await act(this.#desktop, request, ctx.signal);
    } catch (error) {
      if (error instanceof DesktopRefusedError || error instanceof SandboxesError) throw new ToolError(error.message);
      throw error;
    }
  }
}

function image(shot: Screenshot): BetaScreenshotResult {
  // The server says which type its image is ("image/png"): passed on as it said it.
  return { data: base64(shot.image), mediaType: shot.mimeType as BetaScreenshotResult["mediaType"] };
}

/** A point of the model's, in the screen's pixels: whole numbers, as the API takes them. */
function point(coordinate: unknown, field: string): PointInput {
  const [x, y] = numbers(coordinate, 2, `${field}: two numbers, [x, y]`) as Pair;
  return { x, y };
}

/**
 * The model's list of `length` numbers, rounded to whole ones. Its shape is checked, not its values:
 * a value the screen does not have is the server's to refuse.
 */
function numbers(value: unknown, length: number, expected: string): number[] {
  if (!Array.isArray(value) || value.length !== length || !value.every((n) => Number.isFinite(n))) {
    throw new ToolError(expected);
  }
  return value.map((n: number) => Math.round(n));
}

/** Wheel clicks in the direction the model named: down and right are positive. */
function wheel(input: BetaComputerScrollInput): { down: number } | { right: number } {
  const clicks = Math.round(input.scroll_amount);
  // The sign of a wheel action is its direction: a negative amount would scroll against the one named.
  if (!(clicks >= 0)) throw new ToolError("scroll_amount: wheel clicks, 0 or more");
  switch (input.scroll_direction) {
    case "up":
      return { down: -clicks };
    case "down":
      return { down: clicks };
    case "left":
      return { right: -clicks };
    case "right":
      return { right: clicks };
    default:
      throw new ToolError("scroll_direction: up, down, left or right");
  }
}

/** Keys held through a click, drag or scroll, when the model named any. */
function held(text: string | null | undefined): { holdKeys?: string } {
  return text ? { holdKeys: text } : {};
}

/**
 * What a request of the runtime API may hold (SandboxRuntimeService's bounds): keys repeated past
 * it could never be sent, and building them could take this process's memory.
 */
const REQUEST_MAX = 1 << 20;

/** The key chord `times` times, one after the other, as press_keys takes several: apart by spaces. */
function repeated(text: string, times: number): string {
  if (!Number.isInteger(times) || times < 1) throw new ToolError("repeat: a whole number, 1 or more");
  if ((text.length + 1) * times > REQUEST_MAX) throw new ToolError("repeat: the keys repeated are more than one call carries");
  return `${text} `.repeat(times - 1) + text;
}

/**
 * The model's seconds as whole milliseconds: a duration the API's field cannot carry (negative, or
 * of years) cannot be sent. How long a wait or hold may be is the server's to judge.
 */
function milliseconds(seconds: number): number {
  const ms = Math.round(seconds * 1000);
  if (!(ms >= 0 && ms <= MILLISECONDS_MAX)) {
    throw new ToolError(`duration: a number of seconds, from 0 to ${Math.floor(MILLISECONDS_MAX / 1000)}`);
  }
  return ms;
}
