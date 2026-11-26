/**
 * One ControlDesktop call, which the drivers over the sandbox's screen (Claude's computer toolset,
 * OpenAI's computer use) make for every action: the screenshot it answers with, or the refusal of
 * the action that failed, in the server's words.
 */
import { Buffer } from "node:buffer";
import type { ControlDesktopRequest, DesktopFailure, Sandboxes, Screenshot } from "pethost/sandboxes";

/**
 * What a driver over the screen calls of the SDK's client. Picked rather than the class itself, so
 * that a client of another release of the SDK, whose class is another type, is taken as well.
 */
export type DesktopClient = Pick<Sandboxes, "controlDesktop">;

/** The desktop of one sandbox, through one client. */
export interface Desktop {
  readonly sandboxes: DesktopClient;
  readonly sandboxId: string;
}

/**
 * The desktop did not do every action of a call: `doneCount` of them were done, and the next failed
 * for `failure` (to branch on), as the message, the server's failure_message, says (prose).
 */
export class DesktopRefusedError extends Error {
  override readonly name = "DesktopRefusedError";
  readonly failure: DesktopFailure | undefined;
  readonly doneCount: number;

  constructor(message: string, failure?: DesktopFailure, doneCount = 0) {
    super(message);
    this.failure = failure;
    this.doneCount = doneCount;
  }
}

/**
 * Does the request's actions in one call and answers with its screenshot: the image, or with
 * skipScreenshot the screen's size and the pointer alone. An action the desktop did not do throws
 * DesktopRefusedError; a call that failed throws the SDK's SandboxesError.
 */
export async function act(
  desktop: Desktop,
  request: Omit<ControlDesktopRequest, "sandboxId">,
  signal?: AbortSignal | null,
): Promise<Screenshot> {
  const sent = request.actions?.length ?? 0;
  const answer = await desktop.sandboxes.controlDesktop(
    { ...request, sandboxId: desktop.sandboxId },
    signal ? { signal } : undefined,
  );
  if (answer.failure !== undefined || answer.doneCount < sent) {
    throw new DesktopRefusedError(
      answer.failureMessage || "The desktop did not do the action.",
      typeof answer.failure === "string" ? answer.failure : undefined,
      answer.doneCount,
    );
  }
  if (answer.screenshot === undefined) throw new DesktopRefusedError("The desktop answered without a screenshot.");
  return answer.screenshot;
}

/** The image's bytes as base64, which both APIs take a screenshot in. */
export function base64(image: Uint8Array): string {
  return Buffer.from(image.buffer, image.byteOffset, image.byteLength).toString("base64");
}
