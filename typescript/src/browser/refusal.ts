/**
 * What a page or the sandbox refused, in words a model may read: no address, no token. Each driver
 * hands it to its model as its provider's own error, Anthropic's ToolError or openai's BrowserError.
 */
export class PageRefusal extends Error {
  override readonly name = "PageRefusal";
}
