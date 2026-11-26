/**
 * A time limit on a question to a page that Playwright gives none (an evaluate, a title): a page
 * busy in a script never answers it, and the call that asked must not wait with it.
 */
export class TimedOut extends Error {
  override readonly name = "TimedOut";
}

/** The promise's value, or TimedOut once `ms` have passed; what it does goes on unwatched. */
export async function bounded<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const limit = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new TimedOut(`no answer within ${ms / 1000} s`)), ms);
  });
  try {
    return await Promise.race([promise, limit]);
  } finally {
    clearTimeout(timer);
  }
}
