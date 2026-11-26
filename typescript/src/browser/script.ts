/**
 * A script of the model's run in a page (javascript_exec, run_script): its last expression's value,
 * as JSON, and the page's exception as the member's error.
 */
import { errors, type Page } from "playwright-core";

import { TimedOut, bounded } from "./bounded.ts";
import { cut } from "./read.ts";
import { PageRefusal } from "./refusal.ts";

/** The script's value as JSON, cut at the size a model reads at once; `undefined` when it has none. */
export async function runScript(page: Page, source: string, ms: number): Promise<string> {
  const value: unknown = await bounded(page.evaluate(source), ms).catch((error: unknown) => {
    // A timeout, or a connection that dropped under it, is the driver's to say, not the script's.
    if (error instanceof errors.TimeoutError || error instanceof TimedOut) throw error;
    if (!page.context().browser()?.isConnected()) throw error;
    throw new PageRefusal(`The script threw: ${firstLine(error)}`);
  });
  const json = JSON.stringify(value, (_, v: unknown) => (typeof v === "bigint" ? v.toString() : v), 2);
  return cut(json ?? "undefined", "return less");
}

function firstLine(error: unknown): string {
  return ((error instanceof Error ? error.message : String(error)).split("\n")[0] ?? "").replace(/^page\.evaluate: /, "");
}
