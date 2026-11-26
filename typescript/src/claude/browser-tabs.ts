/**
 * The tabs as Claude's browser toolset reports them: an entry for each, and the report after every
 * call, with what changed since the last one.
 */
import type { BetaBrowserState } from "@anthropic-ai/sdk/helpers/beta/toolsets";
import type { BetaBrowserStateTabEntry } from "@anthropic-ai/sdk/resources/beta";
import type { Page } from "playwright-core";

import type { Tabs } from "../browser/tabs.ts";

/** The tab's entry as the toolset reports it. */
export async function entry(tabs: Tabs, page: Page): Promise<BetaBrowserStateTabEntry> {
  return { tab_id: tabs.id(page), title: await tabs.title(page), url: page.url(), active: page === tabs.active() };
}

/** Every open tab, in the browser's order. */
export async function entries(tabs: Tabs): Promise<BetaBrowserStateTabEntry[]> {
  return Promise.all(tabs.pages().map((page) => entry(tabs, page)));
}

/**
 * The report after a call: every tab, and what changed since the last report. Each tab that opened
 * since is reported, new_tab's too, of which the SDK keeps the one tab_opened its result must hold.
 */
export async function report(tabs: Tabs): Promise<BetaBrowserState> {
  const { opened, dialogs } = tabs.drain();
  return {
    tabs: await entries(tabs),
    state_changes: [
      ...opened.map((tabId) => ({ type: "tab_opened" as const, tab_id: tabId })),
      ...dialogs.map(({ kind, message }) => ({ type: "dialog_dismissed" as const, kind, message })),
    ],
  };
}
