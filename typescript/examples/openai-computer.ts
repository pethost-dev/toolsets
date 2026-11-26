// OpenAI's computer use on a sandbox's desktop through the openai SDK's ComputerToolset: each
// action the model sends is one ControlDesktop call, and it sees a screenshot of the whole screen
// after each batch, until it answers.
//
//   PETHOST_TOKEN=pth_... OPENAI_API_KEY=... node openai-computer.ts "Open Chrome and find today's top story on news.ycombinator.com"
import OpenAI from "openai";
import { ComputerToolset } from "openai/helpers/computer";
import { Sandboxes } from "pethost/sandboxes";
import { OpenAIComputer } from "pethost-toolsets/openai/computer";

const task = process.argv.slice(2).join(" ") || "Open Chrome, go to pethost.dev and tell me the page's heading.";
const sandboxes = new Sandboxes({ token: process.env.PETHOST_TOKEN! });
const { sandboxId } = await sandboxes.createSandbox({ template: "base" });

try {
  const toolset = new ComputerToolset(new OpenAIComputer({ sandboxes, sandboxId }));
  const response = await toolset.run(
    new OpenAI(),
    {
      model: "gpt-6.2-sol",
      instructions: "You use a Linux desktop with Chrome on it. Do the task, then say what you found.",
      input: task,
    },
    { maxSteps: 50 },
  );
  console.log(response.output_text);
} finally {
  await sandboxes.deleteSandbox({ sandboxId });
}
