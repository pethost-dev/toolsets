// Claude browses with the Chrome of a sandbox through the browser toolset: it reads pages as
// accessibility trees, clicks their elements by ref and looks at screenshots, while the sandbox's
// page in the panel shows a person what it does.
//
//   PETHOST_TOKEN=pth_... ANTHROPIC_API_KEY=... node claude-browser.ts "What does pethost.dev/sandboxes say a sandbox costs?"
import Anthropic from "@anthropic-ai/sdk";
import { Sandboxes } from "pethost/sandboxes";
import { ClaudeBrowser } from "pethost-toolsets/claude/browser";

const task = process.argv.slice(2).join(" ") || "What does pethost.dev/sandboxes say a sandbox costs an hour?";
const sandboxes = new Sandboxes({ token: process.env.PETHOST_TOKEN! });

// The sandbox reaches only the sites the task needs: its egress allow-list holds for the browser
// too, the pages it opens by themselves included.
const { sandboxId, panelUrl } = await sandboxes.createSandbox({
  template: "base",
  settings: { egress: { allow: ["pethost.dev", "*.pethost.dev"] } },
});
console.log("Watch its desktop in the panel:", panelUrl);

const browser = await ClaudeBrowser.connect({ sandboxes, sandboxId });
try {
  const runner = new Anthropic().beta.messages.toolRunner({
    model: "claude-opus-5-5",
    max_tokens: 16000,
    thinking: { type: "adaptive" },
    // A request the model declines is answered by another model rather than refused.
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    tools: [browser],
    messages: [{ role: "user", content: task }],
  });
  for await (const message of runner) {
    if (message.stop_reason === "refusal") console.log("The model declined the task.");
    for (const block of message.content) if (block.type === "text") console.log(block.text);
  }
} finally {
  await browser.close();
  await sandboxes.deleteSandbox({ sandboxId });
}
