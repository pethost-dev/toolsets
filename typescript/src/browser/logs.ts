/**
 * What each tab's pages wrote to the console and requested over the network since the driver
 * connected (read_console, read_network): kept per page, the newest entries of each, and handed
 * over once, each read answering what came since the last.
 */
import type { BrowserContext, ConsoleMessage, Page, Request, WebError } from "playwright-core";

import { cut } from "./read.ts";

/** The entries kept of each page and kind: older ones are dropped, and the read says how many. */
const KEPT = 500;

/** A URL in an entry is cut here: a data: URL can hold a whole file. */
const URL_MAX = 300;

class Entries {
  lines: string[] = [];
  dropped = 0;

  add(line: string): void {
    this.lines.push(line);
    if (this.lines.length > KEPT) {
      this.lines.shift();
      this.dropped++;
    }
  }
}

type Kind = "console" | "network";

export class Logs {
  readonly #entries = new WeakMap<Page, Record<Kind, Entries>>();

  /** Starts recording every page of the context, the ones open now and the ones that open later. */
  constructor(context: BrowserContext) {
    context.on("console", (message) => this.#console(message));
    context.on("weberror", (error) => this.#pageError(error));
    context.on("requestfinished", (request) => void this.#finished(request));
    context.on("requestfailed", (request) => this.#failed(request));
  }

  /**
   * The page's entries of the kind since the last read, one a line, the last `limit` of them when
   * it is given, and none kept after: cut at the size the model reads at once, as a page may log
   * without end.
   */
  read(page: Page, kind: Kind, limit?: number): string {
    const entries = this.#of(page)[kind];
    const kept = limit === undefined ? entries.lines : entries.lines.slice(-limit);
    const dropped = entries.dropped + entries.lines.length - kept.length;
    const lines = dropped > 0 ? [`(${dropped} earlier entries were dropped)`, ...kept] : kept;
    entries.lines = [];
    entries.dropped = 0;
    return lines.length > 0 ? cut(lines.join("\n"), "read it more often") : `No ${kind} entries since the last read.`;
  }

  #of(page: Page): Record<Kind, Entries> {
    let entries = this.#entries.get(page);
    if (entries === undefined) {
      entries = { console: new Entries(), network: new Entries() };
      this.#entries.set(page, entries);
    }
    return entries;
  }

  #console(message: ConsoleMessage): void {
    const page = message.page();
    if (page !== null) this.#of(page).console.add(`[${message.type()}] ${message.text()}`);
  }

  #pageError(error: WebError): void {
    const page = error.page();
    if (page !== null) this.#of(page).console.add(`[uncaught] ${error.error().message}`);
  }

  async #finished(request: Request): Promise<void> {
    const page = pageOf(request);
    if (page === null) return;
    const response = await request.response().catch(() => null);
    const type = response?.headers()["content-type"] ?? "";
    const ms = Math.round(request.timing().responseEnd);
    this.#of(page).network.add(`${request.method()} ${shortUrl(request.url())} ${response?.status() ?? "-"} ${type} ${ms >= 0 ? `${ms} ms` : ""}`.trimEnd());
  }

  #failed(request: Request): void {
    const page = pageOf(request);
    if (page !== null) this.#of(page).network.add(`${request.method()} ${shortUrl(request.url())} failed: ${request.failure()?.errorText ?? "unknown"}`);
  }
}

/** The page a request is of; none for a service worker's. */
function pageOf(request: Request): Page | null {
  try {
    return request.frame().page();
  } catch {
    return null;
  }
}

function shortUrl(url: string): string {
  return url.length > URL_MAX ? `${url.slice(0, URL_MAX)}…` : url;
}
