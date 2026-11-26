/**
 * What a page says in words: its accessibility tree with element refs (read_page), from
 * Playwright's aria snapshot for AI, whose refs Playwright resolves again for an action; and its
 * text (get_page_text). Both are cut to the size the toolset's model reads at once.
 */
import type { Page } from "playwright-core";

import { bounded } from "./bounded.ts";
import { noElement, plainRef } from "./pointer.ts";
import { PageRefusal } from "./refusal.ts";

/** The longest text a reading member answers: read_page's documented cap, and the same for the page's text. */
export const TEXT_MAX = 50_000;

/** read_page's depth when the model gives none. */
const DEFAULT_DEPTH = 15;

const SNAPSHOT_MS = 15_000;

/** Roles a person acts on: what read_page's "interactive" filter keeps, beside what has a pointer cursor. */
const INTERACTIVE: ReadonlySet<string> = new Set([
  "button", "checkbox", "combobox", "link", "listbox", "menuitem", "menuitemcheckbox", "menuitemradio",
  "option", "radio", "searchbox", "slider", "spinbutton", "switch", "tab", "textbox", "treeitem",
]);

/** What to read of a page: the subtree of a ref, how deep, and which of its elements. */
export interface ReadOptions {
  ref?: string | null | undefined;
  /** Levels under the top: absent = 15. */
  depth?: number | null | undefined;
  /** "visible" (absent): what is in the viewport; "interactive": what of that a person acts on; "all". */
  filter?: "visible" | "interactive" | "all" | null | undefined;
}

/** A node of Playwright's aria snapshot as JSON (locator.ariaSnapshotJSON). */
interface AriaNode {
  role: string;
  name?: string;
  ref?: string;
  text?: string;
  url?: string;
  placeholder?: string;
  cursor?: string;
  level?: number;
  checked?: boolean | "mixed";
  pressed?: boolean | "mixed";
  disabled?: boolean;
  expanded?: boolean;
  selected?: boolean;
  box?: { x: number; y: number; width: number; height: number };
  children?: Array<AriaNode | string>;
}

interface Viewport {
  width: number;
  height: number;
}

/**
 * The page's tree, or the subtree of `ref`, down to `depth` levels under its top (0: the top
 * alone): the elements in the viewport, the interactive ones among them, or all. A subtree is cut
 * from a snapshot of the whole page, so that the refs an earlier read gave stay good.
 */
export async function readPage(page: Page, input: ReadOptions): Promise<string> {
  const depth = input.depth ?? DEFAULT_DEPTH;
  if (!(Number.isInteger(depth) && depth >= 0)) throw new PageRefusal("depth: levels under the top, a whole number, 0 or more");
  const filter = input.filter ?? "visible";
  const roots = (await page.ariaSnapshotJSON({ mode: "ai", boxes: filter !== "all", timeout: SNAPSHOT_MS })) as AriaNode[];
  const from = input.ref == null ? roots : [find(roots, plainRef(input.ref)) ?? noElement(input.ref)];
  const viewport = await bounded(page.evaluate(() => ({ width: innerWidth, height: innerHeight })), SNAPSHOT_MS);
  const lines: string[] = [];
  for (const node of from) render(node, { filter, viewport, depth, lines }, 0, 0);
  if (input.ref != null && lines.length === 0 && filter !== "all") {
    return `The element ${input.ref} is out of the viewport: scroll_to it, or read it with filter "all".`;
  }
  return cut(lines.join("\n"), "narrow it with ref or a smaller depth");
}

/**
 * The page's visible text: its one article when it has one, else its main part, else its body. A
 * page of several articles (a feed, a blog's index) is read whole. The Python driver's PAGE_TEXT
 * (toolsets/python/pethost_toolsets/_browser_shared.py) is the same rule.
 */
export async function pageText(page: Page): Promise<string> {
  const text = await bounded(
    page.evaluate(() => {
      const articles = document.querySelectorAll<HTMLElement>("article");
      const root = articles.length === 1 ? articles[0] : (document.querySelector<HTMLElement>("main, [role=main]") ?? document.body);
      return root?.innerText ?? "";
    }),
    SNAPSHOT_MS,
  );
  return cut(text, "read_page with a ref reads one part");
}

/** The text, cut at TEXT_MAX with a line that says so and how to read less. */
export function cut(text: string, hint: string): string {
  if (text.length <= TEXT_MAX) return text;
  return `${text.slice(0, TEXT_MAX)}\n… cut at ${TEXT_MAX} of ${text.length} characters: ${hint}.`;
}

function find(nodes: Array<AriaNode | string>, ref: string): AriaNode | undefined {
  for (const node of nodes) {
    if (typeof node === "string") continue;
    const found = node.ref === ref ? node : find(node.children ?? [], ref);
    if (found !== undefined) return found;
  }
  return undefined;
}

interface Rendering {
  filter: "visible" | "interactive" | "all";
  viewport: Viewport;
  depth: number;
  lines: string[];
}

/**
 * Writes the node, at `level` under the top, and what of its subtree the filter and the depth keep,
 * as Playwright writes an aria snapshot. Under "interactive", only interactive nodes are written,
 * indented by the interactive ones they are in.
 */
function render(node: AriaNode, r: Rendering, level: number, indent: number): void {
  if (r.filter !== "all" && offScreen(node, r.viewport)) return;
  const shown = r.filter !== "interactive" || INTERACTIVE.has(node.role) || node.cursor === "pointer";
  if (shown) r.lines.push(...describe(node, indent));
  // What it holds, its texts too, is a level below it: past the depth once it is at it.
  if (level >= r.depth) return;
  const inner = shown ? indent + 1 : indent;
  const within = frameRendering(node, r);
  for (const child of node.children ?? []) {
    if (typeof child !== "string") render(child, within, level + 1, inner);
    else if (r.filter !== "interactive") r.lines.push(`${pad(inner)}- text: ${child}`);
  }
}

/** What a frame holds is laid out in the frame's own viewport, its box's size: judged against that. */
function frameRendering(node: AriaNode, r: Rendering): Rendering {
  if (node.role !== "iframe" || !laidOut(node.box)) return r;
  return { ...r, viewport: { width: node.box.width, height: node.box.height } };
}

/** The node's line, and its link or placeholder under it. */
function describe(node: AriaNode, indent: number): string[] {
  const flags = [
    node.checked === true ? "[checked]" : node.checked === "mixed" ? "[checked=mixed]" : "",
    node.disabled ? "[disabled]" : "",
    node.expanded ? "[expanded]" : "",
    node.level ? `[level=${node.level}]` : "",
    node.pressed === true ? "[pressed]" : node.pressed === "mixed" ? "[pressed=mixed]" : "",
    node.selected ? "[selected]" : "",
    node.ref ? `[ref=${node.ref}]` : "",
  ].filter(Boolean);
  const name = node.name ? ` ${JSON.stringify(node.name)}` : "";
  const text = node.text ? `: ${node.text}` : "";
  const lines = [`${pad(indent)}- ${[node.role + name, ...flags].join(" ")}${text}`];
  if (node.url !== undefined) lines.push(`${pad(indent + 1)}- /url: ${JSON.stringify(node.url)}`);
  if (node.placeholder !== undefined) lines.push(`${pad(indent + 1)}- /placeholder: ${JSON.stringify(node.placeholder)}`);
  return lines;
}

/**
 * Whether the node is laid out wholly outside the viewport, and nothing in it is inside: a child can
 * be placed elsewhere (fixed, absolute). A node of no size (an option of a closed select) or with no
 * box is where its parent is.
 */
function offScreen(node: AriaNode, viewport: Viewport): boolean {
  return laidOut(node.box) && !onScreen(node, viewport);
}

function onScreen(node: AriaNode, viewport: Viewport): boolean {
  const box = node.box;
  if (laidOut(box) && box.x + box.width > 0 && box.y + box.height > 0 && box.x < viewport.width && box.y < viewport.height) {
    return true;
  }
  // A frame's own box alone is in this viewport: what it holds is placed in the frame's.
  if (node.role === "iframe") return false;
  return (node.children ?? []).some((child) => typeof child !== "string" && onScreen(child, viewport));
}

function laidOut(box: AriaNode["box"]): box is NonNullable<AriaNode["box"]> {
  return box !== undefined && box.width > 0 && box.height > 0;
}

function pad(indent: number): string {
  return "  ".repeat(indent);
}
