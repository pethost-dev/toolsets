/**
 * What OpenAIBrowser's members do on a page beyond the shared helpers (src/browser/), in the terms
 * of the openai SDK's BrowserToolset: its tab state, its images, its scroll by pixels, its wait for
 * text, its select by values, and the notes a member's result carries of what changed meanwhile.
 */
import type { BrowserState } from "openai/helpers/browser";
import type { ResponseInputImageContent } from "openai/resources/responses/responses";
import { errors, type Page } from "playwright-core";

import { bounded } from "../browser/bounded.ts";
import type { Landed } from "../browser/navigate.ts";
import { REF_ACTION_MS, element, scrollPixels, type Direction } from "../browser/pointer.ts";
import { PageRefusal } from "../browser/refusal.ts";
import type { Changes, Tabs } from "../browser/tabs.ts";

/** How much of a dialog's words a note carries: the page wrote them, and may write without end. */
const DIALOG_WORDS_MAX = 300;

/** What a scroll of no amount scrolls: most of the viewport, as Page Down does. */
const PAGE_SHARE = 0.8;

const VIEWPORT_MS = 5000;

/**
 * Every tab, the active one marked. A URL is given whole: the SDK reports its origin alone, or its
 * scheme. One Playwright cannot say (a page between documents) is reported as about:blank, as the
 * SDK takes only a URL it can read and stops the run at another.
 */
export async function tabState(tabs: Tabs): Promise<BrowserState> {
  const active = tabs.active();
  const entries = tabs.pages().map(async (page) => ({
    id: tabs.id(page),
    title: await tabs.title(page),
    url: URL.canParse(page.url()) ? page.url() : "about:blank",
    active: page === active,
  }));
  return { tabs: await Promise.all(entries) };
}

/** A PNG in base64 as the toolset's image, at its own resolution: one image pixel a CSS pixel. */
export function image(png: string): ResponseInputImageContent {
  return { type: "input_image", image_url: `data:image/png;base64,${png}`, detail: "original" };
}

/**
 * What a navigation says beside the tabs' state: the page's failure, else nothing. Where it landed
 * is the state's to tell, as the SDK projects it: the address after a redirect may hold a code or a
 * token of a sign-in, which a result's words would hand the model whole.
 */
export function landed({ status }: Landed): string | undefined {
  return status !== undefined && status >= 400 ? `The page answered HTTP ${status}.` : undefined;
}

/**
 * `pixels` of scrolling in the direction, at the viewport's middle, where the page's own scrolling
 * part most likely is; none given, most of the viewport.
 */
export async function scrollBy(page: Page, direction: Direction, pixels: number): Promise<void> {
  const view = await bounded(page.evaluate(() => ({ width: innerWidth, height: innerHeight })), VIEWPORT_MS);
  const across = direction === "left" || direction === "right" ? view.width : view.height;
  const amount = pixels > 0 ? pixels : Math.round(across * PAGE_SHARE);
  await scrollPixels(page, { x: Math.round(view.width / 2), y: Math.round(view.height / 2) }, direction, amount);
}

/** Waits for an element whose text holds `text` (whitespace and case aside) to show. */
export async function waitForText(page: Page, text: string, ms: number): Promise<void> {
  try {
    await page.getByText(text.replace(/\s+/g, " ").trim()).first().waitFor({ state: "visible", timeout: ms });
  } catch (error) {
    if (error instanceof errors.TimeoutError) throw new PageRefusal(`No text ${JSON.stringify(text)} showed within ${ms} ms.`);
    throw error;
  }
}

/** Picks the options of the select `ref` names whose values or labels are `values`. */
export async function selectValues(page: Page, ref: string, values: readonly string[]): Promise<void> {
  const field = await element(page, ref);
  const options = { timeout: REF_ACTION_MS };
  const missing = await field.evaluate(
    (el, wanted) => {
      if (!(el instanceof HTMLSelectElement)) return null;
      return wanted.filter((value) => ![...el.options].some((o) => o.value === value || o.label === value));
    },
    [...values],
    options,
  );
  // Playwright's selectOption waits for an option that is not there until it times out.
  if (missing === null) throw new PageRefusal(`${ref} is not a select: type fills a text field.`);
  if (missing.length > 0) throw new PageRefusal(`${ref} has no option ${missing.map((v) => JSON.stringify(v)).join(", ")}.`);
  await field.selectOption([...values], options);
}

/** What changed while a member ran, in words its result carries: the tabs the page opened, the dialogs dismissed. */
export function notes({ opened, dialogs }: Changes): string {
  const lines = dialogs.map(({ kind, message }) => {
    const words = message.length > DIALOG_WORDS_MAX ? `${message.slice(0, DIALOG_WORDS_MAX)}…` : message;
    return `The page's ${kind} dialog was dismissed${words ? `: ${JSON.stringify(words)}` : ""}.`;
  });
  if (opened.length > 0) lines.push(`Opened meanwhile: ${opened.join(", ")}.`);
  return lines.join("\n");
}

/**
 * Refuses points out of the viewport, which the browser would take as nowhere: the model's points
 * come from a screenshot of the viewport, and a zoom's region keeps that origin.
 */
export async function inViewport(page: Page, points: readonly { x: number; y: number }[]): Promise<void> {
  const view = await viewport(page);
  for (const { x, y } of points) {
    if (x >= view.width || y >= view.height) {
      throw new PageRefusal(`(${x}, ${y}) is out of the viewport, ${view.width}×${view.height}: take a screenshot for the coordinates.`);
    }
  }
}

/** Refuses a zoom whose region, [left, top, right, bottom], reaches out of the viewport. */
export async function regionInViewport(page: Page, region: readonly number[]): Promise<void> {
  const view = await viewport(page);
  const [left, top, right = 0, bottom = 0] = region;
  if (right > view.width || bottom > view.height) {
    throw new PageRefusal(`region: [${left}, ${top}, ${right}, ${bottom}] reaches out of the viewport, ${view.width}×${view.height}`);
  }
}

function viewport(page: Page): Promise<{ width: number; height: number }> {
  return bounded(page.evaluate(() => ({ width: innerWidth, height: innerHeight })), VIEWPORT_MS);
}

/** The text with a lone surrogate replaced: the SDK refuses a result that is not valid Unicode, and the run with it. */
export function unicode(text: string): string {
  return text.toWellFormed();
}

/** A network line's query string left out: it may hold a token. */
export function withoutQueries(text: string): string {
  return text.replace(/\?\S*/g, "?…");
}

