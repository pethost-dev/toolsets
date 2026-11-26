/**
 * OpenAIComputer: a driver of the openai SDK's ComputerToolset (openai/helpers/computer), the
 * Responses API's computer tool, over the desktop of a Pethost Agent Sandbox. Each action is one
 * ControlDesktop call, and the screenshot after a batch of them is the whole screen, unscaled, so
 * the model's coordinates are the screen's pixels.
 *
 * Only OpenAI's pixels of scrolling are translated here, to wheel clicks. Its key names go to the
 * desktop as the model writes them ("CTRL", "ENTER", "ARROWLEFT"): the desktop reads them. The
 * server judges every action, and an action it refuses throws DesktopRefusedError with its words, which
 * ends the run: the computer tool answers the model with a screenshot alone, and has no way to tell
 * it why.
 */
import type { ComputerDriver, ComputerScreenshot } from "openai/helpers/computer";
import type { ComputerAction } from "openai/resources/responses/responses";
import { MouseButton, type ControlDesktopRequest, type DesktopActionInput, type PointInput } from "pethost/sandboxes";

import { DesktopRefusedError, act, base64, type Desktop, type DesktopClient } from "../desktop.ts";

export { DesktopRefusedError };

/** The options each action gets: the run's signal, which ends a call under way. */
type Options = { signal: AbortSignal | undefined };

export interface OpenAIComputerOptions {
  /** The client the calls go through: `new Sandboxes({ token })` of `pethost/sandboxes`. */
  sandboxes: DesktopClient;
  /** The sandbox whose desktop the model uses. */
  sandboxId: string;
}

/** How long `wait` waits: the model asks for no duration. */
const WAIT_MS = 1000;

/** The pixels of scrolling one wheel click stands for, as OpenAI's own handlers count them. */
const PIXELS_PER_CLICK = 100;

/** OpenAI's button names: the wheel is the middle button. */
const BUTTONS: Record<ComputerAction.Click["button"], MouseButton> = {
  left: MouseButton.LEFT,
  right: MouseButton.RIGHT,
  wheel: MouseButton.MIDDLE,
  back: MouseButton.BACK,
  forward: MouseButton.FORWARD,
};

/**
 * The desktop of one sandbox for `new ComputerToolset(new OpenAIComputer({ sandboxes, sandboxId }))`.
 * It holds nothing to close: the sandbox's desktop runs on after the run.
 */
export class OpenAIComputer implements ComputerDriver {
  readonly #desktop: Desktop;

  constructor(options: OpenAIComputerOptions) {
    this.#desktop = { sandboxes: options.sandboxes, sandboxId: options.sandboxId };
  }

  screenshot = async ({ signal }: Options): Promise<ComputerScreenshot> => {
    const shot = await this.#call({}, signal);
    return { type: "computer_screenshot", image_url: `data:${shot.mimeType};base64,${base64(shot.image)}` };
  };

  click = async (action: ComputerAction.Click, { signal }: Options): Promise<void> => {
    const click = { ...at(action.x, action.y), button: BUTTONS[action.button], holdKeys: chord(action.keys) };
    await this.#do({ click }, signal);
  };

  double_click = async (action: ComputerAction.DoubleClick, { signal }: Options): Promise<void> => {
    await this.#do({ click: { ...at(action.x, action.y), count: 2, holdKeys: chord(action.keys) } }, signal);
  };

  drag = async (action: ComputerAction.Drag, { signal }: Options): Promise<void> => {
    const path = action.path.map((point) => at(point.x, point.y));
    await this.#do({ drag: { path, holdKeys: chord(action.keys) } }, signal);
  };

  /** The keys pressed together, as the model lists them: ["CTRL", "C"] is ctrl+c. */
  keypress = async (action: ComputerAction.Keypress, { signal }: Options): Promise<void> => {
    await this.#do({ pressKeys: chord(action.keys) }, signal);
  };

  move = async (action: ComputerAction.Move, { signal }: Options): Promise<void> => {
    if (action.keys?.length) throw new DesktopRefusedError("The desktop moves the pointer with no keys held: it has no such action.");
    await this.#do({ moveMouse: at(action.x, action.y) }, signal);
  };

  scroll = async (action: ComputerAction.Scroll, { signal }: Options): Promise<void> => {
    const scroll = {
      ...at(action.x, action.y),
      down: clicks(action.scroll_y),
      right: clicks(action.scroll_x),
      holdKeys: chord(action.keys),
    };
    await this.#do({ scroll }, signal);
  };

  type = async (action: ComputerAction.Type, { signal }: Options): Promise<void> => {
    await this.#do({ typeText: action.text }, signal);
  };

  wait = async (_action: ComputerAction.Wait, { signal }: Options): Promise<void> => {
    await this.#do({ waitMs: WAIT_MS }, signal);
  };

  /** One action, with no image back: the toolset asks for the screenshot after a batch's last one. */
  async #do(action: DesktopActionInput, signal: AbortSignal | undefined): Promise<void> {
    await this.#call({ actions: [action], skipScreenshot: true }, signal);
  }

  #call(request: Omit<ControlDesktopRequest, "sandboxId">, signal: AbortSignal | undefined) {
    return act(this.#desktop, request, signal);
  }
}

/** A point of the model's in whole pixels, as the API takes them. */
function at(x: number, y: number): PointInput {
  return { x: Math.round(x), y: Math.round(y) };
}

/**
 * OpenAI's keys pressed together, as press_keys and hold_keys read them. With other keys a letter is
 * the key, not its capital: the model writes ["CTRL", "A"] for ctrl+a, where the desktop reads a
 * lone "A" as the character, shift and all, and ctrl+shift+a opens Chrome's search of its tabs.
 */
function chord(keys: readonly string[] | null | undefined): string {
  const names = keys ?? [];
  const letters = names.length > 1 ? names.map((key) => (/^[A-Za-z]$/.test(key) ? key.toLowerCase() : key)) : names;
  return letters.join("+");
}

/** Pixels of scrolling as wheel clicks: one for any scrolling at all, so that none is lost. */
function clicks(pixels: number): number {
  if (pixels === 0) return 0;
  const whole = Math.round(pixels / PIXELS_PER_CLICK);
  return whole !== 0 ? whole : Math.sign(pixels);
}
