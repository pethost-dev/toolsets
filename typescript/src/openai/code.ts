/**
 * OpenAICode: OpenAI's computer use by code on a Pethost Agent Sandbox. The function tools exec_py
 * and exec_js, which OpenAI's guide recommends for GPT-6 Astra, run in the sandbox's code runtime
 * (pethost-code, in our base): `new ResponsesToolRunner({ functions: code.functions })`.
 *
 * Python drives the desktop with PyAutoGUI, JavaScript the desktop's Chrome with Playwright, and
 * each is a session of the runtime that keeps its variables from one call to the next, until
 * close() stops them or the sandbox stops (a pause keeps them). A call is one RunCommand, with a
 * GetCommand for each 45 s more the code takes, and a ReadFile for each image it displayed. Its
 * output is what the code printed, logged or displayed, its error's stack, or the runtime's words
 * when it could not run the code; a sandbox the API refuses throws the SDK's SandboxesError, which
 * ends the run.
 */
import { Buffer } from "node:buffer";
import { randomBytes } from "node:crypto";

import type { RunnerFunction } from "openai/helpers/responses-tool-runner";
import type {
  FunctionTool,
  ResponseInputImageContent,
  ResponseInputTextContent,
} from "openai/resources/responses/responses";
import { CommandState, SandboxesError, type Command, type Sandboxes } from "pethost/sandboxes";

/** What the driver calls of the SDK's client, picked so that a client of another release is taken too. */
export type CodeClient = Pick<Sandboxes, "runCommand" | "getCommand" | "stopCommand" | "readFile">;

export type Language = "python" | "javascript";

export interface OpenAICodeOptions {
  /** The client the calls go through: `new Sandboxes({ token })` of `pethost/sandboxes`. */
  sandboxes: CodeClient;
  /** The sandbox whose desktop and browser the code drives. */
  sandboxId: string;
  /**
   * The name of the runtime's sessions (one a language), so that another OpenAICode, or a later run,
   * takes up their variables. Absent: a new name.
   */
  session?: string | undefined;
  /** How long one call's code may run: absent = 120 s, 600 at most. */
  timeoutSeconds?: number | undefined;
}

type Item = ResponseInputTextContent | ResponseInputImageContent;

/**
 * How long a run's code has by default, and at most, as the runtime takes it: a computer-use step is
 * seconds long.
 */
const TIMEOUT_SECONDS = 120;
const TIMEOUT_MAX_SECONDS = 600;
/** The longest wait of one RunCommand or GetCommand: the API's. */
const WAIT_SECONDS = 45;
/**
 * What a run may take beside its code's timeout: the runtime's start of a session (the desktop and
 * Chrome first, on a first run), and its own grace and the calls' after the code.
 */
const START_SECONDS = 120;
const FINISH_GRACE_SECONDS = 30;
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
/** The most of a file one ReadFile answers. */
const READ_BYTES = 1n << 20n;
/**
 * What the images of one call may come to, in number and bytes: the runtime writes PNGs of the
 * screen, a few hundred KiB each, and what the sandbox names past these is not read, since the
 * sandbox's answer is the caller's memory to bound.
 */
const IMAGES_MAX = 16;
const IMAGE_BUDGET_BYTES = 32 << 20;

/** Each tool's language and what the model is told of it. */
const TOOLS: Record<"exec_py" | "exec_js", [Language, string]> = {
  exec_py: [
    "python",
    "Run Python in a persistent session on the sandbox's Linux desktop (X11), whose globals the next " +
      "call still has. Ready without imports: pyautogui, to look at and drive the screen (its fail-safe " +
      "is on: the pointer in a corner of the screen stops the code), time, Image (Pillow), log(*values), " +
      "which reports text, and display(image), which shows you a Pillow image: " +
      "display(pyautogui.screenshot()) shows the screen. What the code prints is reported too, and an " +
      "error's traceback.",
  ],
  exec_js: [
    "javascript",
    "Run JavaScript (Node.js; await works at the top level) in a persistent session with Playwright " +
      "attached to the Chrome on the sandbox's desktop. Globals: browser, context (the browser's tabs) " +
      "and page (the tab in use; set it to another to switch), log(...values), which reports text, as " +
      "console.log does, and display(png), which shows you a PNG image: " +
      'display(await page.screenshot()) shows the page. Keep what a later call ' +
      "needs on globalThis: other variables last one call.",
  ],
};

/** exec_py and exec_js on one sandbox. */
export class OpenAICode {
  /** The runtime's sessions' name: pass it as `session` to take up their variables later. */
  readonly session: string;
  readonly #sandboxes: CodeClient;
  readonly #sandboxId: string;
  readonly #timeout: number;

  constructor(options: OpenAICodeOptions) {
    this.#sandboxes = options.sandboxes;
    this.#sandboxId = options.sandboxId;
    this.session = options.session || `openai-${randomBytes(4).toString("hex")}`;
    this.#timeout = options.timeoutSeconds ?? TIMEOUT_SECONDS;
    if (!(this.#timeout > 0 && this.#timeout <= TIMEOUT_MAX_SECONDS)) {
      throw new RangeError(`timeoutSeconds is more than 0 and ${TIMEOUT_MAX_SECONDS} at most: ${this.#timeout}`);
    }
  }

  /** The two tools, for ResponsesToolRunner's `functions`. */
  get functions(): RunnerFunction[] {
    return Object.entries(TOOLS).map(([name, [language, description]]) => ({
      tool: tool(name, description),
      execute: (args, options) => this.run(language, codeOf(args), options?.signal),
    }));
  }

  /** Runs the code in the language's session, and answers the tool's output. */
  async run(language: Language, code: string, signal?: AbortSignal): Promise<Item[]> {
    const options = signal ? { signal } : undefined;
    const started = await this.#sandboxes.runCommand(
      { sandboxId: this.#sandboxId, command: runCommand(language, this.session, this.#timeout), stdin: code, waitSeconds: WAIT_SECONDS },
      options,
    );
    const ended = await this.#finish(started, options);
    const items: Item[] = [];
    let budget = IMAGE_BUDGET_BYTES;
    let images = 0;
    for (const item of answer(ended)) {
      if (item.type === "text") {
        items.push(textItem(item.text));
      } else if (++images > IMAGES_MAX) {
        items.push(textItem(`[An image was left out: a call shows ${IMAGES_MAX} at most.]`));
      } else {
        const [shown, used] = await this.#image(item.path, budget, options);
        budget -= used;
        items.push(shown);
      }
    }
    return items.length > 0 ? items : [textItem("The code ran and wrote nothing.")];
  }

  /** Stops the sessions, their variables with them. The desktop and Chrome run on. */
  async close(): Promise<void> {
    await this.#sandboxes.runCommand({ sandboxId: this.#sandboxId, command: shell(["pethost-code", "stop", `--session=${this.session}`]) });
  }

  async #finish(command: Command, options: { signal: AbortSignal } | undefined): Promise<Command> {
    // As many waits as the run may take, its session's start among them.
    const waits = Math.ceil((START_SECONDS + this.#timeout + FINISH_GRACE_SECONDS) / WAIT_SECONDS);
    for (let i = 0; i < waits && command.state === CommandState.RUNNING; i++) {
      command = await this.#sandboxes.getCommand(
        { sandboxId: this.#sandboxId, commandId: command.commandId, waitSeconds: WAIT_SECONDS },
        options,
      );
    }
    if (command.state === CommandState.RUNNING) {
      command = await this.#sandboxes.stopCommand({ sandboxId: this.#sandboxId, commandId: command.commandId }, options);
    }
    return command;
  }

  /**
   * The image at the path, read a MiB a call, and the bytes it took; a note in its place when it
   * would pass the budget, when its file cannot be read, or when it is not a PNG.
   */
  async #image(path: string, budget: number, options: { signal: AbortSignal } | undefined): Promise<[Item, number]> {
    const parts: Buffer[] = [];
    let read = 0;
    for (;;) {
      let part;
      try {
        part = await this.#sandboxes.readFile(
          { sandboxId: this.#sandboxId, path, offsetBytes: BigInt(read), lengthBytes: READ_BYTES },
          options,
        );
      } catch (error) {
        if (!(error instanceof SandboxesError)) throw error;
        return [textItem(`[An image the code displayed was left out: ${error.message}]`), 0];
      }
      const chunk = part.data !== undefined ? Buffer.from(part.data) : Buffer.from(part.text ?? "", "utf8");
      const size = Math.max(Number(part.sizeBytes), read + chunk.length);
      if (size > budget) {
        return [textItem(`[An image of ${size} bytes was left out: a call's images take ${IMAGE_BUDGET_BYTES >> 20} MiB at most.]`), 0];
      }
      parts.push(chunk);
      read += chunk.length;
      if (chunk.length === 0 || read >= Number(part.sizeBytes)) break;
    }
    const png = Buffer.concat(parts);
    if (!png.subarray(0, PNG.length).equals(PNG)) return [textItem("[An image the code displayed was left out: it is not a PNG.]"), 0];
    return [imageItem(png), read];
  }
}

function tool(name: string, description: string): FunctionTool {
  return {
    type: "function",
    name,
    description,
    strict: true,
    parameters: {
      type: "object",
      properties: { code: { type: "string", description: "The code to run." } },
      required: ["code"],
      additionalProperties: false,
    },
  };
}

function codeOf(args: Record<string, unknown>): string {
  if (typeof args["code"] !== "string") throw new Error("A call of exec_py or exec_js holds its code as the string `code`.");
  return args["code"];
}

/** The run's command line; each value joined to its option, so that none reads as an option. */
function runCommand(language: Language, session: string, timeout: number): string {
  return shell(["pethost-code", "run", `--session=${session}`, `--language=${language}`, `--timeout=${timeout}`]);
}

/** Words joined as bash reads them back: each in single quotes, unless it is plain. */
function shell(words: string[]): string {
  return words.map((word) => (/^[\w@%+=:,./-]+$/.test(word) ? word : `'${word.replaceAll("'", `'"'"'`)}'`)).join(" ");
}

type Answered = { type: "text"; text: string } | { type: "image"; path: string };

/**
 * The run's answer from its command: the runtime's own document when it ran the code, and its words,
 * or the command's end, when it did not.
 */
function answer(ended: Command): Answered[] {
  if (ended.state === CommandState.EXITED && ended.exitCode === 0) {
    // The document is the runtime's last line: a login shell's own words may come before it.
    try {
      const document: unknown = JSON.parse(ended.stdout.trim().split("\n").at(-1) ?? "");
      const output = (document as { output?: unknown } | null)?.output;
      if (Array.isArray(output) && output.every(answered)) return output;
    } catch {
      // Not the runtime's document: said below.
    }
    return [{ type: "text", text: "The runtime's answer could not be read." }];
  }
  return [{ type: "text", text: failure(ended) }];
}

/** An item of the runtime's document, which comes from the sandbox: its shape is checked. */
function answered(item: unknown): item is Answered {
  const { type, text, path } = (item ?? {}) as { type?: unknown; text?: unknown; path?: unknown };
  return (type === "text" && typeof text === "string") || (type === "image" && typeof path === "string");
}

function failure(ended: Command): string {
  const words = ended.stderr.trim();
  if (ended.state === CommandState.EXITED && words) return `The code did not run: ${words}`;
  if (ended.state === CommandState.LOST) {
    return "The run's end is not known: the sandbox lost its memory while it ran. Its session's variables are gone.";
  }
  return `The run ended without an answer (${String(ended.state)}, exit code ${String(ended.exitCode)}). ${words}`.trim();
}

function textItem(text: string): ResponseInputTextContent {
  return { type: "input_text", text };
}

/** An image at its own size: OpenAI's guide asks for detail "original" in computer use. */
function imageItem(png: Buffer): ResponseInputImageContent {
  return { type: "input_image", image_url: `data:image/png;base64,${png.toString("base64")}`, detail: "original" };
}
