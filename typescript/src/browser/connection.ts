/**
 * The connection to a sandbox's browser: a browser link (CreateLink browser), which Playwright
 * connects to over the Chrome DevTools Protocol.
 *
 * A link is a credential for the whole browser and every site it is signed in to. It lives in
 * `connect` alone and is used at once, so it is made valid for a minute; an open connection does
 * not end when its link expires. Playwright's errors name the address they connected to, so an
 * error of a connection is thrown again in the server's words, or with the link's token cut out,
 * and without its cause.
 */
import type { Sandboxes } from "pethost/sandboxes";
import { chromium, type Browser } from "playwright-core";

/** What the browser calls of the SDK's client, picked so that a client of another release is taken too. */
export type BrowserClient = Pick<Sandboxes, "createLink">;

export interface BrowserLink {
  readonly sandboxes: BrowserClient;
  readonly sandboxId: string;
  /** How long each link is valid for a connection to start: absent = 60 s. */
  readonly ttlSeconds?: number | undefined;
}

const LINK_TTL_SECONDS = 60;

/** The browser link was made but did not connect: the message says why, without the link. */
export class BrowserConnectionError extends Error {
  override readonly name = "BrowserConnectionError";
}

/**
 * How long a connection may take to start. The browser starts with the desktop when it does not run,
 * which the server gives 45 s.
 */
const CONNECT_TIMEOUT_MS = 60_000;

/** How long the server may take to say why it refused a link. */
const REFUSAL_MS = 10_000;

/**
 * A new connection to the sandbox's browser, through a link made for it. A link the server refuses
 * throws the SDK's SandboxesError; a connection that fails, BrowserConnectionError.
 */
export async function connect(link: BrowserLink, signal?: AbortSignal | null): Promise<Browser> {
  const { url } = await link.sandboxes.createLink(
    { sandboxId: link.sandboxId, browser: {}, ttlSeconds: link.ttlSeconds ?? LINK_TTL_SECONDS },
    signal ? { signal } : undefined,
  );
  try {
    // noDefaults: the desktop's Chrome keeps its own settings, which a person uses too: its
    // downloads go to ~/Downloads, not to a folder Playwright deletes at the disconnect.
    return await chromium.connectOverCDP(url, { timeout: CONNECT_TIMEOUT_MS, noDefaults: true });
  } catch (error) {
    const why = (await refusal(url)) ?? withoutToken(error, url);
    throw new BrowserConnectionError(`The sandbox's browser did not connect: ${why}`);
  }
}

/**
 * The server's own words for a link it refused ("sandbox … is stopped: resume it …"), which a
 * WebSocket's failure leaves out, saying only its status: the link over http(s) answers
 * <link>/json/version with them (refusalUrl). None when it answers that, or not at all.
 */
async function refusal(url: string): Promise<string | undefined> {
  try {
    const answer = await fetch(refusalUrl(url), { signal: AbortSignal.timeout(REFUSAL_MS) });
    if (answer.ok) return undefined;
    const words = (await firstBytes(answer, REFUSAL_READ_MAX)).trim().split("\n")[0];
    return words ? withoutToken(`${answer.status} ${words}`, url) : undefined;
  } catch {
    return undefined;
  }
}

/** <link>/json/version, over https for a wss: link and over http for a ws: one, as a test server's is. */
function refusalUrl(url: string): URL {
  const link = new URL(url);
  link.protocol = link.protocol === "ws:" ? "http:" : link.protocol === "wss:" ? "https:" : link.protocol;
  link.pathname = `${link.pathname.replace(/\/+$/, "")}/json/version`;
  link.search = "";
  link.hash = "";
  return link;
}

/**
 * What of a refusal is read: its first line is all the model is told, and a link to the sandbox
 * reaches whatever the sandbox runs, which may answer without end.
 */
const REFUSAL_READ_MAX = 4096;

/** At most `max` bytes of an answer's body, as text; the rest is not read. */
async function firstBytes(answer: Response, max: number): Promise<string> {
  const reader = answer.body?.getReader();
  if (!reader) return "";
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (size < max) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    size += value.length;
  }
  await reader.cancel().catch(() => undefined);
  const bytes = new Uint8Array(Math.min(size, max));
  let at = 0;
  for (const chunk of chunks) {
    const part = chunk.subarray(0, bytes.length - at);
    bytes.set(part, at);
    at += part.length;
  }
  return new TextDecoder().decode(bytes);
}

/**
 * The first line of the error's message, the link's token cut out of it wherever it is; a fixed
 * phrase when the token cannot be told.
 */
function withoutToken(error: unknown, url: string): string {
  const token = URL.canParse(url) ? new URL(url).pathname.split("/").filter(Boolean).at(-1) : undefined;
  if (token === undefined || token.length < 8) return "the connection failed.";
  const line = (error instanceof Error ? error.message : String(error)).split("\n")[0] ?? "";
  return line.split(token).join("<token>");
}
