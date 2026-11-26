/**
 * navigate: to an address, or back, forward or reload in the tab's history. It answers once the
 * new document is parsed, not once its images and the rest have loaded.
 */
import { errors, type Page, type Response } from "playwright-core";

import { bounded } from "./bounded.ts";
import { PageRefusal } from "./refusal.ts";

const LOAD_MS = 30_000;

/** How long Chrome's error page may take to show after a load failed. */
const ERROR_PAGE_MS = 2000;

/** The schemes the driver opens. Any other (javascript:, file:, data:, view-source:) is refused. */
const SCHEMES: ReadonlySet<string> = new Set(["http:", "https:"]);

/** Hosts a typed address without a scheme opens over http, as Chrome reads one: the sandbox's own. */
const LOCAL_HOSTS: readonly string[] = ["localhost", "127.0.0.1", "[::1]"];

type Wait = { waitUntil: "commit"; timeout: number };

const HISTORY: ReadonlyMap<string, (page: Page, wait: Wait) => Promise<Response | null>> = new Map([
  ["back", (page: Page, wait: Wait) => page.goBack(wait)],
  ["forward", (page: Page, wait: Wait) => page.goForward(wait)],
  ["reload", (page: Page, wait: Wait) => page.reload(wait)],
]);

/** Where a navigation landed: the address after redirects, its status and its title. */
export interface Landed {
  url: string;
  status?: number | undefined;
  title?: string | undefined;
}

/** Where the tab landed. */
export async function navigate(page: Page, url: string): Promise<Landed> {
  let response: Response | null;
  try {
    const history = HISTORY.get(url.trim().toLowerCase());
    response = history ? await historyStep(page, history) : await page.goto(address(url), { waitUntil: "domcontentloaded", timeout: LOAD_MS });
  } catch (error) {
    if (error instanceof PageRefusal) throw error;
    if (error instanceof errors.TimeoutError) throw new PageRefusal(`The page did not load within ${LOAD_MS / 1000} s.`);
    // Chrome shows its error page a moment after Playwright reports the failure, and that
    // navigation would cut the tab's next one short: it is waited for here.
    await page.waitForURL(/^chrome-error:/, { waitUntil: "commit", timeout: ERROR_PAGE_MS }).catch(() => undefined);
    throw new PageRefusal(`The page did not load${netError(error)}.`);
  }
  const title = await bounded(page.title(), 2000).catch(() => "");
  return { url: page.url(), ...(response ? { status: response.status() } : {}), ...(title ? { title } : {}) };
}

/**
 * A step in the tab's history, done once its document is parsed. A page Chrome brings back from its
 * back-forward cache, which a Chrome Playwright did not start keeps on, fires no load events: the
 * step waits for its commit, then reads the document's state, where Playwright's wait for the
 * events would last until its timeout.
 */
async function historyStep(page: Page, step: (page: Page, wait: Wait) => Promise<Response | null>): Promise<Response | null> {
  const deadline = Date.now() + LOAD_MS;
  const response = await step(page, { waitUntil: "commit", timeout: LOAD_MS });
  // Polled by time, not by animation frame, which Chrome does not run for a window that does not show.
  const wait = { polling: 100, timeout: Math.max(1, deadline - Date.now()) };
  await page.waitForFunction(() => document.readyState !== "loading", undefined, wait);
  return response;
}

/**
 * The address the model wrote, as the browser will open it: about:blank as it is, and with no
 * scheme (a port is no scheme: "localhost:3000") https://, or http:// on the sandbox's own
 * localhost.
 */
function address(url: string): string {
  if (url === "about:blank") return url;
  const local = LOCAL_HOSTS.some((host) => url === host || url.startsWith(`${host}:`) || url.startsWith(`${host}/`));
  const withScheme = /^[a-z][a-z0-9+.-]*:(?!\d)/i.test(url) ? url : `${local ? "http" : "https"}://${url}`;
  if (!URL.canParse(withScheme) || !SCHEMES.has(new URL(withScheme).protocol)) {
    throw new PageRefusal("navigate opens http and https addresses, back, forward and reload.");
  }
  return withScheme;
}

/** The network's error code of a failed load ("net::ERR_NAME_NOT_RESOLVED"), which names no address. */
function netError(error: unknown): string {
  const code = error instanceof Error ? /net::ERR_[A-Z_]+/.exec(error.message)?.[0] : undefined;
  return code ? `: ${code}` : "";
}
