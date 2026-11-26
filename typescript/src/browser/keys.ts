/**
 * The browser toolset's key names, which follow xdotool's ("Return", "BackSpace", "ctrl+a",
 * "Page_Down"), as Playwright's keyboard names them ("Enter", "Backspace", "Control+a",
 * "PageDown"), and the keys of a chord held down on a page. A name not here goes to Playwright as
 * written ("a", "Enter", "F5"), which refuses one it does not know.
 */
import type { Page } from "playwright-core";

import { PageRefusal } from "./refusal.ts";

/** Modifier keys as Playwright's click options take them. */
export type Modifier = "Alt" | "Control" | "Meta" | "Shift";

/**
 * Every alias, written in lower case, and the key Playwright calls it: the same table, entry for
 * entry, as the Python driver's (toolsets/python/pethost_toolsets/_browser_input.py, KEYS and
 * MODIFIERS), so that a model's call means one thing in either.
 */
const NAMES: Readonly<Record<string, string>> = {
  return: "Enter",
  enter: "Enter",
  kp_enter: "Enter",
  backspace: "Backspace",
  esc: "Escape",
  escape: "Escape",
  tab: "Tab",
  space: "Space",
  delete: "Delete",
  del: "Delete",
  insert: "Insert",
  home: "Home",
  end: "End",
  page_up: "PageUp",
  pageup: "PageUp",
  prior: "PageUp",
  page_down: "PageDown",
  pagedown: "PageDown",
  next: "PageDown",
  up: "ArrowUp",
  arrowup: "ArrowUp",
  down: "ArrowDown",
  arrowdown: "ArrowDown",
  left: "ArrowLeft",
  arrowleft: "ArrowLeft",
  right: "ArrowRight",
  arrowright: "ArrowRight",
  caps_lock: "CapsLock",
  capslock: "CapsLock",
  ctrl: "Control",
  control: "Control",
  shift: "Shift",
  alt: "Alt",
  option: "Alt",
  // The model's cmd is the key of a shortcut (cmd+a, cmd+click), which in the sandbox's Linux Chrome
  // is ctrl. Not "ControlOrMeta": Playwright resolves that by the system of the machine the
  // driver runs on, not the browser's. The desktop's own names make cmd the Super key instead, as
  // it presses X's keys, not Chrome's shortcuts.
  cmd: "Control",
  command: "Control",
  meta: "Meta",
  super: "Meta",
  win: "Meta",
  windows: "Meta",
};

const MODIFIERS: ReadonlySet<string> = new Set(["Alt", "Control", "Meta", "Shift"]);

/** One key's name as Playwright knows it. */
export function keyName(name: string): string {
  const alias = NAMES[name.toLowerCase()];
  if (alias !== undefined) return alias;
  if (/^f([1-9]|1[0-9]|2[0-4])$/i.test(name)) return name.toUpperCase();
  return name;
}

const NO_KEY = "text: the key or chord to press, such as Return or ctrl+a";

/**
 * The keys of a chord ("ctrl+shift+t"), each as Playwright names it ("Control", "Shift", "t"). A
 * "+" that comes first or right after another is the key itself: "+", "ctrl++".
 */
export function chord(text: string): string[] {
  const names: string[] = [];
  let rest = text.trim();
  while (rest !== "") {
    const cut = rest.indexOf("+", 1);
    if (cut < 0) {
      names.push(rest);
      break;
    }
    names.push(rest.slice(0, cut));
    rest = rest.slice(cut + 1);
    if (rest === "") throw new PageRefusal(`text: a key is missing after the last "+" of ${JSON.stringify(text)}`);
  }
  if (names.length === 0) throw new PageRefusal(NO_KEY);
  return names.map(keyName);
}

/**
 * Keys pressed together, given one a name ("CTRL", "a"), each as Playwright names it. Among others,
 * a letter is the key, not its capital: ["CTRL", "A"] is Control and a, where a lone "A" types the
 * capital.
 */
export function keyNames(names: readonly string[]): string[] {
  if (names.length === 0 || names.some((name) => name.trim() === "")) {
    throw new PageRefusal('keys: the keys to press together, such as ["Control", "a"]');
  }
  const together = names.length > 1;
  return names.map((name) => keyName(together && /^[A-Z]$/.test(name) ? name.toLowerCase() : name.trim()));
}

/** The chords of a key member, one after the other: "ctrl+a BackSpace" is two presses. */
export function chords(text: string): string[][] {
  const presses = text.trim().split(/\s+/).filter(Boolean);
  if (presses.length === 0) throw new PageRefusal(NO_KEY);
  return presses.map(chord);
}

/**
 * The keys pressed down in order while `act` runs, then let go in reverse: each one that went down,
 * whatever failed. Playwright's own press leaves the keys before a name it does not know pressed
 * ("ctrl+NotAKey"), and every later click and key of the connection would hold them.
 */
export async function holding<T>(page: Page, keys: readonly string[], act: () => Promise<T>): Promise<T> {
  const down: string[] = [];
  try {
    for (const key of keys) {
      await page.keyboard.down(key);
      down.push(key);
    }
    return await act();
  } finally {
    for (const key of down.reverse()) await page.keyboard.up(key);
  }
}

/** The modifiers of a click (`modifiers`: "shift", "ctrl+shift", "cmd+alt"); none when absent. */
export function modifiers(text: string | null | undefined): Modifier[] {
  if (!text) return [];
  return text.split("+").map((name) => {
    const key = keyName(name.trim());
    if (!MODIFIERS.has(key)) throw new PageRefusal(`modifiers: "${name}" is not one of shift, ctrl, alt and cmd`);
    return key as Modifier;
  });
}
