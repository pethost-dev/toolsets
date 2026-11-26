// OpenAI's model browses with the Chrome of a sandbox through the openai SDK's BrowserToolset: it
// reads pages as accessibility trees, clicks their elements by ref and looks at screenshots, while
// the sandbox's page in the panel shows a person what it does.
//
//   PETHOST_TOKEN=pth_... OPENAI_API_KEY=... node openai-browser.ts "What does pethost.dev/sandboxes say a sandbox costs?"
import OpenAI from "openai";
import { BrowserToolset } from "openai/helpers/browser";
import { ResponsesToolRunner } from "openai/helpers/responses-tool-runner";
import { Sandboxes } from "pethost/sandboxes";
import { OpenAIBrowser } from "pethost-toolsets/openai/browser";

const task = process.argv.slice(2).join(" ") || "What does pethost.dev/sandboxes say a sandbox costs an hour?";
const sandboxes = new Sandboxes({ token: process.env.PETHOST_TOKEN! });

// The sandbox reaches only the sites the task needs: its egress allow-list holds for the browser
// too, the pages it opens by themselves included. urlPolicy below holds the model's own navigations
// to the same.
const { sandboxId, panelUrl } = await sandboxes.createSandbox({
  template: "base",
  settings: { egress: { allow: ["pethost.dev", "*.pethost.dev"] } },
});
console.log("Watch its desktop in the panel:", panelUrl);

const browser = await OpenAIBrowser.connect({ sandboxes, sandboxId });
const toolset = new BrowserToolset(browser, {
  // Every action the model takes is approved here; a person's prompt would go in its place.
  confirm: () => true,
  urlPolicy: (_, url) => URL.canParse(url) && new URL(url).protocol === "https:" && /(^|\.)pethost\.dev$/.test(new URL(url).hostname),
});
try {
  const response = await new ResponsesToolRunner({ browser: toolset }).run(
    new OpenAI(),
    { model: "gpt-6.2-astra", input: task },
    { maxSteps: 40 },
  );
  console.log(response.output_text);
} finally {
  toolset.close();
  await browser.close();
  await sandboxes.deleteSandbox({ sandboxId });
}
