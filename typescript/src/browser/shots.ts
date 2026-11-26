/**
 * Pictures of a page, each a PNG in base64: its viewport, at one image pixel a CSS pixel, so that
 * the model's points are the page's; and a region of it rendered larger (zoom), as sharp as the
 * page's own text.
 */
import type { Page } from "playwright-core";

import { bounded } from "./bounded.ts";
import { PageRefusal } from "./refusal.ts";

const SHOT_MS = 30_000;

/** The viewport as it is now: a PNG, in base64. */
export async function screenshot(page: Page): Promise<string> {
  const image = await page.screenshot({ type: "png", scale: "css", timeout: SHOT_MS });
  return image.toString("base64");
}

/**
 * The region [x0, y0, x1, y1] of the viewport, rendered at the scale that fills the viewport's size
 * with it: Chrome draws it again larger, rather than enlarging the pixels of a screenshot.
 */
export async function zoom(page: Page, region: readonly number[]): Promise<string> {
  const shape = "region: four numbers, [x0, y0, x1, y1], with x1 above x0 and y1 above y0";
  if (!Array.isArray(region) || region.length !== 4 || !region.every((n) => Number.isFinite(n))) throw new PageRefusal(shape);
  const [x0, y0, x1, y1] = region as [number, number, number, number];
  if (!(x1 > x0 && y1 > y0)) throw new PageRefusal(shape);
  const width = x1 - x0;
  const height = y1 - y0;
  const view = await bounded(
    page.evaluate(() => ({ width: innerWidth, height: innerHeight, left: visualViewport?.pageLeft ?? scrollX, top: visualViewport?.pageTop ?? scrollY })),
    SHOT_MS,
  );
  const scale = Math.min(view.width / width, view.height / height);
  const session = await page.context().newCDPSession(page);
  try {
    // The protocol's clip is in the document's pixels: the viewport's point plus where it has scrolled to.
    const clip = { x: x0 + view.left, y: y0 + view.top, width, height, scale };
    const { data } = await bounded(session.send("Page.captureScreenshot", { format: "png", clip }), SHOT_MS);
    return data;
  } finally {
    await session.detach().catch(() => undefined);
  }
}
