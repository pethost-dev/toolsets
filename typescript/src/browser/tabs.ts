/**
 * The tabs of the sandbox's browser as a browser toolset names them: an id for each page, the
 * active tab (where an action without a tab_id goes), and what changed since it was last asked:
 * the tabs that opened, the dialogs the driver dismissed. Each driver says them in its toolset's
 * words (claude/browser-tabs.ts, openai/browser.ts).
 */
import type { BrowserContext, Dialog, Page } from "playwright-core";

import { bounded } from "./bounded.ts";
import { PageRefusal } from "./refusal.ts";

/** How long a page may take to say its title or its target: a busy page is reported without. */
const PAGE_QUESTION_MS = 2000;

/** A native dialog of a page's, which the driver dismissed: its kind ("alert", "confirm", "prompt", "beforeunload") and its words. */
export interface Dismissed {
  kind: string;
  message: string;
}

/** What changed since the last drain: the ids of the tabs that opened, the dialogs dismissed. */
export interface Changes {
  opened: string[];
  dialogs: Dismissed[];
}

/**
 * What one connection's tabs leave to the next connection of the same driver, so that the model's
 * tab ids go on naming the same tabs after a connection dropped: each tab id by Chrome's own id of
 * its tab (its target), which outlives a connection, the active tab's, and the next number.
 */
export interface TabMemory {
  readonly ids: Map<string, string>;
  active: string | undefined;
  next: number;
}

export function tabMemory(): TabMemory {
  return { ids: new Map(), active: undefined, next: 1 };
}

export class Tabs {
  readonly #context: BrowserContext;
  readonly #memory: TabMemory;
  readonly #ids = new WeakMap<Page, string>();
  readonly #targets = new WeakMap<Page, Promise<string | undefined>>();
  #active: Page | undefined;
  /** The pages of the last drain, against which tabs opened since are found. */
  #reported: Set<Page>;
  #dialogs: Dismissed[] = [];

  /**
   * The tabs of a browser just connected to, each with the id an earlier connection gave it, else a
   * new one in the browser's order; the active tab is the one that was, else the last. A page sees
   * every tab as shown once Playwright is attached, so the tab the window shows cannot be told.
   * Native dialogs are dismissed from now on, and reported.
   */
  static async of(context: BrowserContext, memory: TabMemory): Promise<Tabs> {
    const tabs = new Tabs(context, memory);
    const pages = context.pages();
    const targets = await Promise.all(pages.map((page) => tabs.#target(page)));
    pages.forEach((page, i) => {
      const known = targets[i] === undefined ? undefined : memory.ids.get(targets[i]);
      if (known !== undefined) tabs.#ids.set(page, known);
    });
    for (const page of pages) tabs.id(page);
    const active = pages.find((_, i) => targets[i] !== undefined && targets[i] === memory.active);
    tabs.activate(active ?? pages.at(-1));
    context.on("page", (page) => void tabs.#target(page));
    context.on("dialog", (dialog) => tabs.#dismiss(dialog));
    return tabs;
  }

  private constructor(context: BrowserContext, memory: TabMemory) {
    this.#context = context;
    this.#memory = memory;
    this.#reported = new Set(context.pages());
  }

  /**
   * The page `tabId` names, else the active one; with no tab open, a new one, which is reported as
   * opened. An unknown id is the model's error.
   */
  async page(tabId: string | null | undefined): Promise<Page> {
    const pages = this.#context.pages();
    if (tabId != null) {
      const page = pages.find((p) => this.#ids.get(p) === tabId);
      if (page === undefined) throw new PageRefusal(`There is no tab ${tabId}: list_tabs shows the open ones.`);
      return page;
    }
    return this.active() ?? this.open();
  }

  /** Makes the page the active tab: where actions without a tab_id go from now on. */
  activate(page: Page | undefined): void {
    this.#active = page;
    if (page === undefined) return;
    void this.#target(page).then((target) => {
      if (this.#active === page) this.#memory.active = target;
    });
  }

  /** A new tab, the active one. */
  async open(): Promise<Page> {
    const page = await this.#context.newPage();
    this.activate(page);
    return page;
  }

  /** Every open tab, in the browser's order. */
  pages(): Page[] {
    return this.#context.pages();
  }

  /** The active page while it is open; once it closes, the last tab, as a browser shows next. */
  active(): Page | undefined {
    const pages = this.#context.pages();
    if (this.#active === undefined || !pages.includes(this.#active)) this.activate(pages.at(-1));
    return this.#active;
  }

  /** The page's title; empty when the page does not say it in time (busy in a script). */
  async title(page: Page): Promise<string> {
    return (await bounded(page.title(), PAGE_QUESTION_MS).catch(() => undefined)) ?? "";
  }

  /**
   * What changed since the last drain, and nothing kept after: each tab that opened since, a tab a
   * member opened too, and each dialog dismissed.
   */
  drain(): Changes {
    const pages = this.#context.pages();
    const opened = pages.filter((page) => !this.#reported.has(page)).map((page) => this.id(page));
    const dialogs = this.#dialogs;
    this.#reported = new Set(pages);
    this.#dialogs = [];
    return { opened, dialogs };
  }

  /** The page's tab id: the one it has, else the next, which the memory keeps by its target. */
  id(page: Page): string {
    const known = this.#ids.get(page);
    if (known !== undefined) return known;
    const id = `tab_${this.#memory.next++}`;
    this.#ids.set(page, id);
    void this.#target(page).then((target) => {
      if (target !== undefined) this.#memory.ids.set(target, id);
    });
    return id;
  }

  /** Chrome's id of the page's tab, asked once; none when the page cannot say (it closed). */
  #target(page: Page): Promise<string | undefined> {
    let target = this.#targets.get(page);
    if (target === undefined) {
      target = targetId(page);
      this.#targets.set(page, target);
    }
    return target;
  }

  /** No member answers a dialog: it is dismissed, so that the page goes on, and the model is told. */
  #dismiss(dialog: Dialog): void {
    this.#dialogs.push({ kind: dialog.type(), message: dialog.message() });
    dialog.dismiss().catch(() => undefined);
  }
}

/** The target id of the page's tab, through a protocol session of its own. */
async function targetId(page: Page): Promise<string | undefined> {
  try {
    const session = await page.context().newCDPSession(page);
    try {
      const { targetInfo } = await bounded(session.send("Target.getTargetInfo"), PAGE_QUESTION_MS);
      return targetInfo.targetId;
    } finally {
      void session.detach().catch(() => undefined);
    }
  } catch {
    return undefined;
  }
}
