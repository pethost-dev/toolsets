// OpenAI's computer use by code on a sandbox, as OpenAI's guide recommends for GPT-6 Astra: the
// model writes Python, which drives the desktop with PyAutoGUI, and JavaScript, which drives its
// Chrome with Playwright, and the sandbox's code runtime runs each in a session that keeps its
// variables.
//
//   PETHOST_TOKEN=pth_... OPENAI_API_KEY=... node openai-code.ts "Find ..."
import OpenAI from "openai";
import { ResponsesToolRunner } from "openai/helpers/responses-tool-runner";
import { Sandboxes } from "pethost/sandboxes";
import { OpenAICode } from "pethost-toolsets/openai/code";

const task = process.argv.slice(2).join(" ") || "Open pethost.dev in the browser and tell me what the page's heading says.";
const sandboxes = new Sandboxes({ token: process.env.PETHOST_TOKEN! });
const { sandboxId } = await sandboxes.createSandbox({ template: "base" });
const code = new OpenAICode({ sandboxes, sandboxId });

try {
  const runner = new ResponsesToolRunner({ functions: code.functions });
  const response = await runner.run(
    new OpenAI(),
    {
      model: "gpt-6-astra",
      instructions: "You use a Linux desktop with Chrome on it, by writing code with your tools.",
      input: task,
    },
    { maxSteps: 50 },
  );
  console.log(response.output_text);
} finally {
  await code.close();
  await sandboxes.deleteSandbox({ sandboxId });
}
