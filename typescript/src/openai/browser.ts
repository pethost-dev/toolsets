/**
 * OpenAIBrowser: a driver of the openai SDK's BrowserToolset (openai/helpers/browser) over the
 * Chrome on the desktop of a Pethost Agent Sandbox, driven by Playwright over a browser link
 * (CreateLink browser), as ClaudeBrowser is. It is the browser a desktop link shows and
 * ControlDesktop acts on, with its profile on the sandbox's disk: the sites it is signed in to stay
 * signed in.
 *
 * Its 17 standard members are served (read_page's refs are Playwright's aria refs, which the
 * element members take), and of the opt-in ones click_at, hover_at, drag_path, hold_keys,
 * set_checked, read_diagnostics and run_script, which BrowserToolset turns on only when asked
 * (`additionalMembers`). Not served, so not offered: find (it needs a model to match words to
 * elements), read_page_scoped, and upload_file and download_file (the browser is not on the
 * machine the grants are). A member's result notes the dialogs the page opened, which are
 * dismissed, and the tabs it opened meanwhile; the console and the network are recorded from the
 * connection on, for read_diagnostics. What fails reaches the model as a BrowserError in the
 * page's or the sandbox's words, never with the link.
 */
import { setTimeout as sleep } from "node:timers/promises";

import { BrowserError, type BrowserArguments, type BrowserDriver, type BrowserState, type BrowserTextReadV1 } from "openai/helpers/browser";
import type { ResponseInputImageContent } from "openai/resources/responses/responses";
import type { Page } from "playwright-core";

import { BrowserConnectionError, type BrowserClient } from "../browser/connection.ts";
import { Driving, type Session } from "../browser/driving.ts";
import { holding, keyNames } from "../browser/keys.ts";
import { navigate } from "../browser/navigate.ts";
import { REF_ACTION_MS, click, dragPath, element, pointer } from "../browser/pointer.ts";
import { pageText, readPage } from "../browser/read.ts";
import { runScript } from "../browser/script.ts";
import { screenshot, zoom } from "../browser/shots.ts";
import { image, inViewport, landed, regionInViewport, notes, scrollBy, selectValues, tabState, unicode, waitForText, withoutQueries } from "./browser-parts.ts";

/** The second argument of every member: the run's signal. */
type Exec = { signal: AbortSignal | undefined };

/** What a key member that failed adds: what fails is nearly always a key name Playwright does not know. */
const KEY_NAMES = "keys are named as Enter, Tab, Escape, Backspace, ArrowDown, PageUp, F5, Control or a";

/** What `connect` throws for a link the server refused or a connection that failed, in the server's words. */
export { BrowserConnectionError };

export interface OpenAIBrowserOptions {
  /** The client the links are made through: `new Sandboxes({ token })` of `pethost/sandboxes`. */
  sandboxes: BrowserClient;
  /** The sandbox whose browser the model uses. */
  sandboxId: string;
  /** How long each browser link is valid for its connection to start: absent = 60 s. */
  ttlSeconds?: number | undefined;
}

/**
 * The driver over a sandbox's Chrome. Make it with `OpenAIBrowser.connect`, give it to
 * `new BrowserToolset(driver, { confirm, urlPolicy })`, and `close()` it when done, which
 * disconnects and leaves the browser running. A connection that drops (the sandbox's server
 * restarted) is made again at the next member.
 */
export class OpenAIBrowser implements BrowserDriver {
  readonly #driving: Driving;

  /** Connects to the sandbox's browser, starting it with the desktop if it does not run (some seconds). */
  static async connect(options: OpenAIBrowserOptions): Promise<OpenAIBrowser> {
    const browser = new OpenAIBrowser(options);
    await browser.#driving.open(undefined);
    return browser;
  }

  private constructor({ sandboxes, sandboxId, ttlSeconds }: OpenAIBrowserOptions) {
    this.#driving = new Driving({ sandboxes, sandboxId, ttlSeconds }, { record: () => true, fail: (message) => new BrowserError(message) });
  }

  /** Disconnects; the browser and its tabs stay as they are. Close the toolset first, and await its calls. */
  async close(): Promise<void> {
    await this.#driving.close();
  }

  /**
   * The tabs, which the toolset reads before and after every member, the connection made again if
   * it dropped; none while the browser cannot be reached, which the member then says, rather than
   * an error that would stop the run.
   */
  async state(options?: { signal: AbortSignal | undefined }): Promise<BrowserState> {
    try {
      return await tabState((await this.#driving.open(options?.signal)).tabs);
    } catch {
      return { tabs: [] };
    }
  }

  async navigate(args: BrowserArguments<"navigate">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "navigate", async (page) => landed(await navigate(page, args.url)));
  }

  async read_page(args: BrowserArguments<"read_page">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "read_page", (page) => readPage(page, { filter: args.filter }));
  }

  async get_page_text(args: BrowserArguments<"get_page_text">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "get_page_text", (page) => pageText(page));
  }

  async click(args: BrowserArguments<"click">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "click", async (page) => {
      await (await element(page, args.target)).click({ timeout: REF_ACTION_MS });
    });
  }

  /** Fills the referenced field with the text, or types it at the focus. */
  async type(args: BrowserArguments<"type">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "type", async (page) => {
      if (args.target === null) await page.keyboard.type(args.text);
      else await (await element(page, args.target)).fill(args.text, { timeout: REF_ACTION_MS });
    });
  }

  async key(args: BrowserArguments<"key">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "key", (page) => holding(page, keyNames(args.keys), async () => undefined), KEY_NAMES);
  }

  /** Scrolls `amount` CSS pixels, at the viewport's middle; 0, most of the viewport. */
  async scroll(args: BrowserArguments<"scroll">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "scroll", (page) => scrollBy(page, args.direction, args.amount));
  }

  async scroll_to(args: BrowserArguments<"scroll_to">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "scroll_to", async (page) => {
      await (await element(page, args.target)).scrollIntoViewIfNeeded({ timeout: REF_ACTION_MS });
    });
  }

  async wait_for(args: BrowserArguments<"wait_for">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "wait_for", (page) => waitForText(page, args.text, args.timeout_ms));
  }

  async select_option(args: BrowserArguments<"select_option">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "select_option", (page) => selectValues(page, args.target, args.values));
  }

  async hover(args: BrowserArguments<"hover">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "hover", async (page) => {
      await (await element(page, args.target)).hover({ timeout: REF_ACTION_MS });
    });
  }

  async screenshot(args: BrowserArguments<"screenshot">, { signal }: Exec): Promise<ResponseInputImageContent> {
    return this.#driving.on(signal, args.tab_id, "screenshot", async (page) => image(await screenshot(page)));
  }

  async zoom(args: BrowserArguments<"zoom">, { signal }: Exec): Promise<ResponseInputImageContent> {
    return this.#driving.on(signal, args.tab_id, "zoom", async (page) => {
      await regionInViewport(page, args.region);
      return image(await zoom(page, args.region));
    });
  }

  /** A new tab, the active one, at the URL when one is given. */
  async new_tab(args: BrowserArguments<"new_tab">, { signal }: Exec): Promise<string> {
    const { tabs } = await this.#driving.ready(signal);
    return this.#driving.guard("new_tab", async () => {
      const page = await tabs.open();
      const failed = args.url === null ? undefined : landed(await navigate(page, args.url));
      const where = failed ? ` ${failed}` : "";
      const { opened, dialogs } = tabs.drain();
      const meanwhile = notes({ opened: opened.filter((id) => id !== tabs.id(page)), dialogs });
      return [`Opened ${tabs.id(page)}, the active tab.${where}`, meanwhile].filter(Boolean).join("\n");
    });
  }

  async switch_tab(args: BrowserArguments<"switch_tab">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "switch_tab", async () => undefined);
  }

  async close_tab(args: BrowserArguments<"close_tab">, { signal }: Exec): Promise<string | undefined> {
    const { tabs } = await this.#driving.ready(signal);
    await this.#driving.guard("close_tab", () => tabs.close(args.tab_id));
    return notes(tabs.drain()) || undefined;
  }

  async click_at(args: BrowserArguments<"click_at">, { signal }: Exec): Promise<string | undefined> {
    const target = { type: "coordinate" as const, x: args.x, y: args.y };
    const options = { button: args.button, clickCount: args.click_count, modifiers: args.keys };
    return this.#act(signal, args.tab_id, "click_at", async (page) => {
      await inViewport(page, [target]);
      await click(page, target, options);
    });
  }

  async hover_at(args: BrowserArguments<"hover_at">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "hover_at", async (page) => {
      await inViewport(page, [args]);
      await pointer(page, { type: "coordinate", x: args.x, y: args.y });
    });
  }

  async drag_path(args: BrowserArguments<"drag_path">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "drag_path", async (page) => {
      await inViewport(page, args.path);
      await dragPath(page, args.path, args.keys);
    });
  }

  async hold_keys(args: BrowserArguments<"hold_keys">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "hold_keys", (page) =>
      holding(page, keyNames(args.keys), () => sleep(args.duration_ms, undefined, { signal })),
    KEY_NAMES);
  }

  async set_checked(args: BrowserArguments<"set_checked">, { signal }: Exec): Promise<string | undefined> {
    return this.#act(signal, args.tab_id, "set_checked", async (page) => {
      await (await element(page, args.target)).setChecked(args.checked, { timeout: REF_ACTION_MS });
    });
  }

  /**
   * The tab's newest console or network entries since the last read, `limit` of them at most; a
   * request's query string is left out, as it may hold a token.
   */
  async read_diagnostics(args: BrowserArguments<"read_diagnostics">, { signal }: Exec): Promise<BrowserTextReadV1> {
    return this.#driving.on(signal, args.tab_id, "read_diagnostics", async (page, session) => {
      const text = logsOf(session).read(page, args.source, args.limit);
      return {
        version: 1 as const,
        text: unicode(args.source === "network" ? withoutQueries(text) : text),
        elements: [],
        omitted: [],
      };
    });
  }

  /** The script's last expression's value, as JSON; the page's exception is the member's error. */
  async run_script(args: BrowserArguments<"run_script">, { signal }: Exec): Promise<string> {
    return this.#driving.on(signal, args.tab_id, "run_script", async (page) => unicode(await runScript(page, args.source, args.timeout_ms)));
  }

  /**
   * Runs `act` on the tab (Driving.on), and answers its words, a read's even when empty, with notes
   * of what changed meanwhile: a dialog the page opened, a tab. An action with neither answers none.
   */
  async #act(
    signal: AbortSignal | undefined,
    tabId: string | null,
    what: string,
    act: (page: Page) => Promise<string | void>,
    hint?: string,
  ): Promise<string | undefined> {
    return this.#driving.on(signal, tabId, what, async (page, { tabs }) => {
      const words = await act(page);
      const meanwhile = notes(tabs.drain());
      if (typeof words !== "string") return meanwhile || undefined;
      return meanwhile ? `${words}\n\n${meanwhile}` : words;
    }, hint);
  }
}

function logsOf(session: Session): NonNullable<Session["logs"]> {
  // Recorded from every connection on (record: () => true).
  if (session.logs === undefined) throw new BrowserError("The console and the network are not recorded.");
  return session.logs;
}
