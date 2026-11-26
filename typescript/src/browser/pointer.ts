/**
 * The mouse on a page: at a point of the viewport, in CSS pixels as a viewport screenshot shows
 * them, or on an element by the ref a read_page gave (Playwright's aria refs), which Playwright
 * scrolls into view and waits to take the action.
 */
import type { Locator, Page } from "playwright-core";

import { bounded } from "./bounded.ts";
import { holding, type Modifier } from "./keys.ts";
import { PageRefusal } from "./refusal.ts";

/** A point of the viewport, in CSS pixels, as Claude's browser toolset writes one. */
export interface CoordinateTarget {
  type: "coordinate";
  x: number;
  y: number;
}

/** An element by the ref a read_page gave, or a point. */
export type ClickTarget = { type: "ref"; ref: string } | CoordinateTarget;

export type Direction = "up" | "down" | "left" | "right";

/** How long an element by ref may take to be ready for an action: a hidden or covered one fails then. */
export const REF_ACTION_MS = 5000;

/** The pixels of scrolling one wheel notch stands for. */
const PIXELS_PER_NOTCH = 100;

/** How long a scroll waits for the page to say its scrolling ended: the page's own limit, and a second more. */
const SETTLE_MS = 2500;

export interface ClickOptions {
  button: "left" | "right" | "middle";
  clickCount: number;
  modifiers: Modifier[];
}

/** The element the ref names in the page's latest read_page, or the model's error when there is none. */
export async function element(page: Page, ref: string): Promise<Locator> {
  const locator = page.getByRef(plainRef(ref));
  const found = await locator.count().catch((error: unknown) => {
    // A ref of an earlier document names a frame the page no longer has, which Playwright throws
    // for; a connection that dropped is not that.
    if (!page.context().browser()?.isConnected()) throw error;
    return 0;
  });
  if (found === 0) noElement(ref);
  return locator;
}

/** A ref as Playwright resolves it ("e5"), from the forms the model may copy from read_page's text ("[ref=e5]", "ref=e5"). */
export function plainRef(ref: string): string {
  return ref.trim().replace(/^\[+|\]+$/g, "").replace(/^ref=/, "");
}

/** The model's error for a ref the page no longer has. */
export function noElement(ref: string): never {
  throw new PageRefusal(`There is no element ${ref} on the page now: call read_page again for current refs.`);
}

/** A click at the target, the modifiers held through it. */
export async function click(page: Page, target: ClickTarget, options: ClickOptions): Promise<void> {
  if (target.type === "ref") {
    await (await element(page, target.ref)).click({ ...options, timeout: REF_ACTION_MS });
    return;
  }
  const { x, y } = point(target);
  await holding(page, options.modifiers, () =>
    page.mouse.click(x, y, { button: options.button, clickCount: options.clickCount }),
  );
}

/** The pointer over the target, no button pressed. */
export async function hover(page: Page, target: ClickTarget): Promise<void> {
  if (target.type === "ref") {
    await (await element(page, target.ref)).hover({ timeout: REF_ACTION_MS });
    return;
  }
  const { x, y } = point(target);
  await page.mouse.move(x, y);
}

/** The pointer to a point, then the left button down or up there, or neither. */
export async function pointer(page: Page, target: CoordinateTarget, button?: "down" | "up"): Promise<void> {
  const { x, y } = point(target);
  await page.mouse.move(x, y);
  if (button === "down") await page.mouse.down();
  if (button === "up") await page.mouse.up();
}

/** A press at `from`, a move through the steps a page sees as a drag, and a release at `to`. */
export async function drag(page: Page, from: CoordinateTarget, to: CoordinateTarget): Promise<void> {
  await dragPath(page, [point(from), point(to)], []);
}

/**
 * A press at the path's first point, a move through each next one in the steps a page sees as a
 * drag, and a release at its last, the modifiers held through it.
 */
export async function dragPath(page: Page, path: ReadonlyArray<{ x: number; y: number }>, held: Modifier[]): Promise<void> {
  const [start, ...rest] = path;
  if (start === undefined || rest.length === 0) throw new PageRefusal("path: two points at least");
  await holding(page, held, async () => {
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    try {
      for (const next of rest) await page.mouse.move(next.x, next.y, { steps: Math.max(1, Math.round(DRAG_STEPS / rest.length)) });
    } finally {
      // A button left down would hold for every later click and key of the connection.
      await page.mouse.up();
    }
  });
}

/** How many moves a drag takes from its start to its end, through all its points. */
const DRAG_STEPS = 10;

/** Wheel notches at a point, in the direction the model named. */
export async function scroll(
  page: Page,
  target: CoordinateTarget,
  direction: Direction,
  notches: number,
): Promise<void> {
  const { x, y } = point(target);
  await scrollPixels(page, { x, y }, direction, notches * PIXELS_PER_NOTCH);
}

/** The wheel at a point, `pixels` of scrolling in the direction, then the wait for it to end. */
export async function scrollPixels(page: Page, at: { x: number; y: number }, direction: Direction, pixels: number): Promise<void> {
  const { x, y } = at;
  const [dx, dy] =
    direction === "up" ? [0, -pixels]
    : direction === "down" ? [0, pixels]
    : direction === "left" ? [-pixels, 0]
    : direction === "right" ? [pixels, 0]
    : unknownDirection();
  await page.mouse.move(x, y);
  await page.mouse.wheel(dx, dy);
  await settled(page);
}

/**
 * Waits for the scrolling a wheel started to end, as Chrome scrolls smoothly over some hundred
 * milliseconds: until no element or the page has scrolled for a moment, a second and a half at most.
 * Without it, a screenshot taken next catches the page midway. A page busy in a script answers
 * nothing, and the scroll ends without the wait.
 */
async function settled(page: Page): Promise<void> {
  const waited = page.evaluate(
    ({ quietMs, maxMs }) =>
      new Promise<void>((resolve) => {
        let quiet = setTimeout(done, quietMs);
        const limit = setTimeout(done, maxMs);
        function moved(): void {
          clearTimeout(quiet);
          quiet = setTimeout(done, quietMs);
        }
        function done(): void {
          clearTimeout(quiet);
          clearTimeout(limit);
          removeEventListener("scroll", moved, true);
          resolve();
        }
        addEventListener("scroll", moved, { capture: true, passive: true });
      }),
    { quietMs: 150, maxMs: 1500 },
  );
  await bounded(waited, SETTLE_MS).catch(() => undefined);
}

/** A point of the model's: its shape is checked, as the page would take anything. */
function point(target: CoordinateTarget | ClickTarget): { x: number; y: number } {
  if (target?.type !== "coordinate" || !Number.isFinite(target.x) || !Number.isFinite(target.y)) {
    throw new PageRefusal('target: a point, {"type": "coordinate", "x": …, "y": …}, in viewport pixels');
  }
  return { x: target.x, y: target.y };
}

function unknownDirection(): never {
  throw new PageRefusal("scroll_direction: up, down, left or right");
}
