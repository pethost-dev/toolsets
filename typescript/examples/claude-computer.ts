// Claude uses a sandbox's desktop through the computer toolset: the tool runner sends each of its
// actions to the sandbox and gives it the screenshots back, until it answers.
//
//   PETHOST_TOKEN=pth_... ANTHROPIC_API_KEY=... node claude-computer.ts "Open Chrome and find today's top story on news.ycombinator.com"
import Anthropic from "@anthropic-ai/sdk";
import { Sandboxes } from "pethost/sandboxes";
import { ClaudeComputer } from "pethost-toolsets/claude/computer";

const task = process.argv.slice(2).join(" ") || "Open Chrome, go to pethost.dev and tell me the page's heading.";
const sandboxes = new Sandboxes({ token: process.env.PETHOST_TOKEN! });
const { sandboxId } = await sandboxes.createSandbox({ template: "base" });

// The sandbox is kept apart by its VM, so every action is approved here. Ask a person instead when
// the desktop is signed in to accounts whose actions matter.
const computer = new ClaudeComputer({ sandboxes, sandboxId, confirm: () => true });
try {
  const runner = new Anthropic().beta.messages.toolRunner({
    model: "claude-opus-5-5",
    max_tokens: 16000,
    thinking: { type: "adaptive" },
    // A request the model declines is answered by another model rather than refused.
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    tools: [computer],
    messages: [{ role: "user", content: task }],
  });
  for await (const message of runner) {
    if (message.stop_reason === "refusal") console.log("The model declined the task.");
    for (const block of message.content) if (block.type === "text") console.log(block.text);
  }
} finally {
  await computer.close();
  await sandboxes.deleteSandbox({ sandboxId });
}
