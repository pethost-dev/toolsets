/**
 * What a browser driver holds of the sandbox's browser, whatever its model's toolset: one
 * connection at a time, made again after one dropped, the tabs it knows, the logs it records, and
 * how a member's work is run, a failure of Playwright's said in fixed words. Each driver passes
 * `fail`, which makes its toolset's error (Anthropic's ToolError, openai's BrowserError) from words
 * a model may read.
 */
import { SandboxesError } from "pethost/sandboxes";
import { errors, type Browser, type BrowserContext, type Page } from "playwright-core";

import { TimedOut } from "./bounded.ts";
import { BrowserConnectionError, connect, type BrowserLink } from "./connection.ts";
import { Logs } from "./logs.ts";
import { PageRefusal } from "./refusal.ts";
import { Tabs, tabMemory } from "./tabs.ts";

/** One connection to the browser, and what is known of it while it lasts. */
export interface Session {
  browser: Browser;
  context: BrowserContext;
  tabs: Tabs;
  logs: Logs | undefined;
}

export interface DrivingOptions {
  /** Whether a new connection records the console and the network. */
  record: () => boolean;
  /** The toolset's error, made from words a model may read. */
  fail: (message: string) => Error;
}

export class Driving {
  readonly #link: BrowserLink;
  readonly #options: DrivingOptions;
  /** What every connection's tabs leave to the next, the tab ids above all. */
  readonly #memory = tabMemory();
  #session: Session | undefined;

  constructor(link: BrowserLink, options: DrivingOptions) {
    this.#link = link;
    this.#options = options;
  }

  /** The connection while it is up; none before the first or once it dropped. */
  get session(): Session | undefined {
    return this.#session?.browser.isConnected() ? this.#session : undefined;
  }

  /** The connection, made now if there is none or it dropped. A link refused or a connection that failed throws as it is. */
  async open(signal: AbortSignal | null | undefined): Promise<Session> {
    if (this.#session?.browser.isConnected()) return this.#session;
    const browser = await connect(this.#link, signal);
    try {
      // The browser's default context is its profile, on the sandbox's disk; Chrome always has one.
      const context = browser.contexts()[0];
      if (context === undefined) throw new BrowserConnectionError("The sandbox's browser has no profile to drive.");
      const logs = this.#options.record() ? new Logs(context) : undefined;
      this.#session = { browser, context, tabs: await Tabs.of(context, this.#memory), logs };
      return this.#session;
    } catch (error) {
      // A connection left open would keep the sandbox awake as a session.
      await browser.close().catch(() => undefined);
      throw error;
    }
  }

  /** The connection for a member: one that cannot be made is the member's error, in its words. */
  async ready(signal: AbortSignal | null | undefined): Promise<Session> {
    try {
      return await this.open(signal);
    } catch (error) {
      if (error instanceof SandboxesError || error instanceof BrowserConnectionError) throw this.#options.fail(error.message);
      throw error;
    }
  }

  /**
   * Runs `act` on the tab `tabId` names, else the active one. The tab is brought to the front first
   * and becomes the active one: Chrome draws, and so pictures, only the tab its window shows.
   */
  async on<T>(
    signal: AbortSignal | null | undefined,
    tabId: string | null | undefined,
    what: string,
    act: (page: Page, session: Session) => Promise<T>,
    hint?: string,
  ): Promise<T> {
    const session = await this.ready(signal);
    return this.guard(what, async () => {
      const page = await session.tabs.page(tabId);
      await page.bringToFront();
      session.tabs.activate(page);
      return act(page, session);
    }, hint);
  }

  /**
   * The member's work: a PageRefusal is the member's error in its words, and any other failure of
   * Playwright's in fixed ones, as its messages hold page content and addresses.
   */
  async guard<T>(what: string, act: () => Promise<T>, hint?: string): Promise<T> {
    const { fail } = this.#options;
    try {
      return await act();
    } catch (error) {
      if (error instanceof PageRefusal) throw fail(error.message);
      if (error instanceof errors.TimeoutError || error instanceof TimedOut) throw fail(`${what} timed out.`);
      if (!this.#session?.browser.isConnected()) throw fail(`${what} failed: the connection to the browser was lost. Try again.`);
      throw fail(hint ? `${what} failed: ${hint}.` : `${what} failed.`);
    }
  }

  /** Disconnects; the browser and its tabs stay as they are. */
  async close(): Promise<void> {
    const session = this.#session;
    this.#session = undefined;
    await session?.browser.close();
  }
}
