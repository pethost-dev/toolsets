/**
 * ClaudeBrowser: Claude's browser toolset (browser_toolset_20260801) over the Chrome on the desktop
 * of a Pethost Agent Sandbox, driven by Playwright over a browser link (CreateLink browser). It is
 * the browser a desktop link shows and ControlDesktop acts on, with its profile on the sandbox's
 * disk: the sites it is signed in to stay signed in.
 *
 * Adapted from Anthropic's example driver over the Chrome DevTools Protocol
 * (github.com/anthropics/claude-quickstarts, browser-toolset; MIT License, Copyright (c) 2023
 * Anthropic): its shape of a driver, its addresses without a scheme read as https, its reading of
 * a page's text. The rest is Playwright's: aria snapshots and their refs, the mouse and keyboard.
 *
 * find is not served (it needs a model to match words to elements), nor file_upload (the browser is
 * not on the machine the files are): the SDK reports both as disabled. read_console, read_network and
 * javascript_exec are served and off unless `configs` turns them on, as the API has them.
 */
import { setTimeout as sleep } from "node:timers/promises";

import {
  BetaAbstractBrowserToolset20260801,
  ToolError,
  type BetaBrowserNavigateResult,
  type BetaBrowserState,
  type BetaBrowserToolsetOptions,
  type BetaScreenshotResult,
  type BetaToolsetCallContext,
} from "@anthropic-ai/sdk/helpers/beta/toolsets";
import type * as Beta from "@anthropic-ai/sdk/resources/beta";
import type { Page } from "playwright-core";

import { BrowserConnectionError, type BrowserClient } from "../browser/connection.ts";
import { Driving, type Session } from "../browser/driving.ts";
import { FORM_VALUES, formInput } from "../browser/form.ts";
import { chord, chords, holding, modifiers } from "../browser/keys.ts";
import type { Logs } from "../browser/logs.ts";
import { navigate } from "../browser/navigate.ts";
import { REF_ACTION_MS, click, drag, element, hover, pointer, scroll, type ClickOptions } from "../browser/pointer.ts";
import { pageText, readPage } from "../browser/read.ts";
import { PageRefusal } from "../browser/refusal.ts";
import { runScript } from "../browser/script.ts";
import { screenshot, zoom } from "../browser/shots.ts";
import { entries, entry, report } from "./browser-tabs.ts";

type Ctx = BetaToolsetCallContext;

/** The longest wait or key hold: the toolset's documented maximum. */
const HOLD_MAX_SECONDS = 30;

/** What a key member that failed adds: what fails is nearly always a key name Playwright does not know. */
const KEY_NAMES = 'keys are named as Enter, Tab, Escape, Backspace, ArrowDown, PageUp, F5 or a, joined by "+" in a chord';

/**
 * The most times a key member presses its keys: the range Anthropic's drivers give repeat, 1 to 100.
 * The presses go to the page one after another, and the tab waits for the last.
 */
const REPEAT_MAX = 100;

/** How long a script of javascript_exec may run. */
const SCRIPT_MS = 30_000;

/** What `connect` throws for a link the server refused or a connection that failed, in the server's words. */
export { BrowserConnectionError };

export interface ClaudeBrowserOptions extends Omit<BetaBrowserToolsetOptions, "browserState" | "filePolicy"> {
  /** The client the links are made through: `new Sandboxes({ token })` of `pethost/sandboxes`. */
  sandboxes: BrowserClient;
  /** The sandbox whose browser the model uses. */
  sandboxId: string;
  /** How long each browser link is valid for its connection to start: absent = 60 s. */
  ttlSeconds?: number | undefined;
}

/**
 * The browser toolset over a sandbox's Chrome. Make it with `ClaudeBrowser.connect`, pass it in
 * `tools` of the tool runner, and `close()` it when done, which disconnects and leaves the browser
 * running. A connection that drops (the sandbox's server restarted) is made again at the next call.
 */
export class ClaudeBrowser extends BetaAbstractBrowserToolset20260801 {
  readonly #driving: Driving;

  /** Connects to the sandbox's browser, starting it with the desktop if it does not run (some seconds). */
  static async connect(options: ClaudeBrowserOptions): Promise<ClaudeBrowser> {
    const browser = new ClaudeBrowser(options);
    await browser.#driving.open(undefined);
    return browser;
  }

  private constructor({ sandboxes, sandboxId, ttlSeconds, ...options }: ClaudeBrowserOptions) {
    super({ ...options, browserState: () => this.#state() });
    this.#driving = new Driving(
      { sandboxes, sandboxId, ttlSeconds },
      {
        record: () => this.configs?.read_console?.enabled === true || this.configs?.read_network?.enabled === true,
        fail: (message) => new ToolError(message),
      },
    );
  }

  /** Disconnects once the calls in flight are done; the browser and its tabs stay as they are. */
  override async close(): Promise<void> {
    await super.close();
    await this.#driving.close();
  }

  protected override async navigate(ctx: Ctx, input: Beta.BetaBrowserNavigateInput): Promise<BetaBrowserNavigateResult> {
    return this.#on(ctx, input.tab_id, "navigate", (page) => navigate(page, input.url));
  }

  protected override async screenshot(ctx: Ctx, input: Beta.BetaBrowserScreenshotInput): Promise<BetaScreenshotResult> {
    return this.#on(ctx, input.tab_id, "screenshot", async (page) => png(await screenshot(page)));
  }

  protected override async zoom(ctx: Ctx, input: Beta.BetaBrowserZoomInput): Promise<BetaScreenshotResult> {
    return this.#on(ctx, input.tab_id, "zoom", async (page) => png(await zoom(page, input.region)));
  }

  protected override async left_click(ctx: Ctx, input: Beta.BetaBrowserLeftClickInput): Promise<void> {
    await this.#click(ctx, input, { button: "left", clickCount: 1 });
  }

  protected override async right_click(ctx: Ctx, input: Beta.BetaBrowserRightClickInput): Promise<void> {
    await this.#click(ctx, input, { button: "right", clickCount: 1 });
  }

  protected override async middle_click(ctx: Ctx, input: Beta.BetaBrowserMiddleClickInput): Promise<void> {
    await this.#click(ctx, input, { button: "middle", clickCount: 1 });
  }

  protected override async double_click(ctx: Ctx, input: Beta.BetaBrowserDoubleClickInput): Promise<void> {
    await this.#click(ctx, input, { button: "left", clickCount: 2 });
  }

  protected override async triple_click(ctx: Ctx, input: Beta.BetaBrowserTripleClickInput): Promise<void> {
    await this.#click(ctx, input, { button: "left", clickCount: 3 });
  }

  protected override async hover(ctx: Ctx, input: Beta.BetaBrowserHoverInput): Promise<void> {
    await this.#on(ctx, input.tab_id, "hover", (page) => hover(page, input.target));
  }

  protected override async left_click_drag(ctx: Ctx, input: Beta.BetaBrowserLeftClickDragInput): Promise<void> {
    await this.#on(ctx, input.tab_id, "left_click_drag", (page) => drag(page, input.from, input.target));
  }

  protected override async left_mouse_down(ctx: Ctx, input: Beta.BetaBrowserLeftMouseDownInput): Promise<void> {
    await this.#on(ctx, input.tab_id, "left_mouse_down", (page) => pointer(page, input.target, "down"));
  }

  protected override async left_mouse_up(ctx: Ctx, input: Beta.BetaBrowserLeftMouseUpInput): Promise<void> {
    await this.#on(ctx, input.tab_id, "left_mouse_up", (page) => pointer(page, input.target, "up"));
  }

  protected override async mouse_move(ctx: Ctx, input: Beta.BetaBrowserMouseMoveInput): Promise<void> {
    await this.#on(ctx, input.tab_id, "mouse_move", (page) => pointer(page, input.target));
  }

  protected override async scroll(ctx: Ctx, input: Beta.BetaBrowserScrollInput): Promise<void> {
    const notches = input.scroll_amount ?? 3;
    if (!(notches >= 1 && notches <= 10)) throw new ToolError("scroll_amount: wheel notches, from 1 to 10");
    await this.#on(ctx, input.tab_id, "scroll", (page) => scroll(page, input.target, input.scroll_direction, notches));
  }

  protected override async scroll_to(ctx: Ctx, input: Beta.BetaBrowserScrollToInput): Promise<void> {
    await this.#on(ctx, input.tab_id, "scroll_to", async (page) =>
      (await element(page, input.target.ref)).scrollIntoViewIfNeeded({ timeout: REF_ACTION_MS }),
    );
  }

  protected override async type_(ctx: Ctx, input: Beta.BetaBrowserTypeInput): Promise<void> {
    await this.#on(ctx, input.tab_id, "type", (page) => page.keyboard.type(input.text));
  }

  protected override async key(ctx: Ctx, input: Beta.BetaBrowserKeyInput): Promise<void> {
    const presses = chords(input.text);
    const times = input.repeat ?? 1;
    if (!(Number.isInteger(times) && times >= 1 && times <= REPEAT_MAX)) {
      throw new ToolError(`repeat: a whole number, from 1 to ${REPEAT_MAX}`);
    }
    await this.#on(ctx, input.tab_id, "key", async (page) => {
      for (let i = 0; i < times; i++) for (const press of presses) await holding(page, press, async () => undefined);
    }, KEY_NAMES);
  }

  protected override async hold_key(ctx: Ctx, input: Beta.BetaBrowserHoldKeyInput): Promise<void> {
    const ms = holdMs(input.duration);
    const keys = chord(input.text);
    await this.#on(ctx, input.tab_id, "hold_key", (page) =>
      holding(page, keys, () => sleep(ms, undefined, { signal: ctx.signal ?? undefined })),
    KEY_NAMES);
  }

  protected override async form_input(ctx: Ctx, input: Beta.BetaBrowserFormInputInput): Promise<void> {
    await this.#on(ctx, input.tab_id, "form_input", (page) => formInput(page, input.target.ref, input.value), FORM_VALUES);
  }

  protected override async read_page(ctx: Ctx, input: Beta.BetaBrowserReadPageInput): Promise<string> {
    return this.#on(ctx, input.tab_id, "read_page", (page) => readPage(page, input));
  }

  protected override async get_page_text(ctx: Ctx, input: Beta.BetaBrowserGetPageTextInput): Promise<string> {
    return this.#on(ctx, input.tab_id, "get_page_text", (page) => pageText(page));
  }

  protected override async wait(ctx: Ctx, input: Beta.BetaBrowserWaitInput): Promise<void> {
    await sleep(holdMs(input.duration), undefined, { signal: ctx.signal ?? undefined });
  }

  protected override async read_console(ctx: Ctx, input: Beta.BetaBrowserReadConsoleInput): Promise<string> {
    return this.#on(ctx, input.tab_id, "read_console", async (page, session) => logs(session).read(page, "console"));
  }

  protected override async read_network(ctx: Ctx, input: Beta.BetaBrowserReadNetworkInput): Promise<string> {
    return this.#on(ctx, input.tab_id, "read_network", async (page, session) => logs(session).read(page, "network"));
  }

  /** The script's last expression's value, as JSON; a page's exception is the member's error. */
  protected override async javascript_exec(ctx: Ctx, input: Beta.BetaBrowserJavascriptExecInput): Promise<string> {
    return this.#on(ctx, input.tab_id, "javascript_exec", (page) => runScript(page, input.text, SCRIPT_MS));
  }

  protected override async new_tab(ctx: Ctx): Promise<Beta.BetaBrowserStateTabEntry> {
    const { tabs } = await this.#driving.ready(ctx.signal);
    return this.#driving.guard("new_tab", async () => entry(tabs, await tabs.open()));
  }

  protected override async list_tabs(ctx: Ctx): Promise<Beta.BetaBrowserStateTabEntry[]> {
    return entries((await this.#driving.ready(ctx.signal)).tabs);
  }

  protected override async switch_tab(ctx: Ctx, input: Beta.BetaBrowserSwitchTabInput): Promise<Beta.BetaBrowserStateTabEntry> {
    return this.#on(ctx, input.tab_id, "switch_tab", (page, { tabs }) => entry(tabs, page));
  }

  protected override async close_tab(ctx: Ctx, input: Beta.BetaBrowserCloseTabInput): Promise<void> {
    const { tabs } = await this.#driving.ready(ctx.signal);
    await this.#driving.guard("close_tab", () => tabs.close(input.tab_id));
  }

  async #click(ctx: Ctx, input: Beta.BetaBrowserLeftClickInput, options: Omit<ClickOptions, "modifiers">): Promise<void> {
    const held = modifiers(input.modifiers);
    await this.#on(ctx, input.tab_id, "click", (page) => click(page, input.target, { ...options, modifiers: held }));
  }

  /** Runs `act` on the tab `tabId` names, else the active one, which it brings to the front (Driving.on). */
  async #on<T>(
    ctx: Ctx,
    tabId: string | null | undefined,
    what: string,
    act: (page: Page, session: Session) => Promise<T>,
    hint?: string,
  ): Promise<T> {
    return this.#driving.on(ctx.signal, tabId, what, act, hint);
  }

  /** The report after every call; with no connection, no tabs, rather than an error that would end the run. */
  async #state(): Promise<BetaBrowserState> {
    const session = this.#driving.session;
    try {
      return session ? await report(session.tabs) : { tabs: [] };
    } catch {
      return { tabs: [] };
    }
  }
}

function png(data: string): BetaScreenshotResult {
  return { data, mediaType: "image/png" };
}

function logs(session: Session): Logs {
  if (session.logs === undefined) throw new PageRefusal("The console and the network are not recorded: configs turns them on.");
  return session.logs;
}

/** A wait or hold of the model's in milliseconds, within the toolset's maximum. */
function holdMs(seconds: number): number {
  if (!(seconds >= 0 && seconds <= HOLD_MAX_SECONDS)) {
    throw new ToolError(`duration: seconds, from 0 to ${HOLD_MAX_SECONDS}`);
  }
  return Math.round(seconds * 1000);
}
