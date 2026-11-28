# pethost-toolsets for TypeScript

Drivers that give an AI agent the desktop and the browser of a
[Pethost Agent Sandbox](https://pethost.dev/sandboxes/): a Firecracker microVM with its own
kernel, and Chrome on a 1280×800 desktop.

| Driver | For | Over |
|---|---|---|
| `ClaudeComputer` (`pethost-toolsets/claude/computer`) | Claude's computer toolset, `computer_toolset_20260801` | the sandbox's screen: ControlDesktop |
| `ClaudeBrowser` (`pethost-toolsets/claude/browser`) | Claude's browser toolset, `browser_toolset_20260801` | the sandbox's Chrome, through Playwright and a browser link |
| `OpenAIComputer` (`pethost-toolsets/openai/computer`) | the openai SDK's `ComputerToolset`, OpenAI's computer tool | the sandbox's screen: ControlDesktop |
| `OpenAIBrowser` (`pethost-toolsets/openai/browser`) | the openai SDK's `BrowserToolset` | the sandbox's Chrome, through Playwright and a browser link |
| `OpenAICode` (`pethost-toolsets/openai/code`) | OpenAI's computer use by code: `exec_py` and `exec_js` | the sandbox's code runtime, through RunCommand |

They act on the same desktop and the same Chrome: a person watching the sandbox's page in the
panel sees what the agent does, and the sites Chrome is signed in to stay signed in, on the
sandbox's disk. The docs walk through all of them:
[Claude's and OpenAI's computer use](https://pethost.dev/docs/sandboxes/claude-and-openai/).

## Install

Node.js 22 or later, the package with what the drivers you use need beside it:

```sh
npm install pethost-toolsets @anthropic-ai/sdk   # ClaudeComputer
npm install pethost-toolsets openai              # OpenAIComputer, OpenAICode
npm install playwright-core                      # ClaudeBrowser and OpenAIBrowser too
```

It brings the Pethost SDK (`pethost` 0.10, the first with browser links). `@anthropic-ai/sdk`
(1.x), `openai` (7.64 or later) and `playwright-core` (1.65 or later) are optional peer
dependencies: your program and the drivers share one copy of each, and a driver needs only its
own. Playwright only connects to the sandbox's Chrome, so it downloads no browser. A token for
the API is made in the panel's Settings, under "API tokens".

## Claude's computer toolset

```ts
import Anthropic from "@anthropic-ai/sdk";
import { Sandboxes } from "pethost/sandboxes";
import { ClaudeComputer } from "pethost-toolsets/claude/computer";

const sandboxes = new Sandboxes({ token: process.env.PETHOST_TOKEN! });
const { sandboxId } = await sandboxes.createSandbox({ template: "base" });

const computer = new ClaudeComputer({ sandboxes, sandboxId, confirm: () => true });
try {
  const runner = new Anthropic().beta.messages.toolRunner({
    model: "claude-opus-5-5",
    max_tokens: 16000,
    tools: [computer],
    messages: [{ role: "user", content: "Open Chrome, go to pethost.dev and tell me the page's heading." }],
  });
  for await (const message of runner) console.log(message.content);
} finally {
  await computer.close();
}
```

Each action Claude takes is one call to the sandbox; only `screenshot` and `zoom` bring an image
back. The screen fits every current model's image limits, so the points Claude sends are the
screen's pixels, after a zoom too. The sandbox judges every action, and an action it refuses (a
point off the screen, a key it does not know) reaches Claude as that action's error, in the
sandbox's words.

The Anthropic SDK asks for a `confirm` callable while `type`, `key` and `hold_key` are on. The
example approves everything, as the sandbox is kept apart by its VM; ask a person instead when
the desktop is signed in to accounts whose actions matter, or turn those members off in `configs`.

## Claude's browser toolset

```ts
import { ClaudeBrowser } from "pethost-toolsets/claude/browser";

const browser = await ClaudeBrowser.connect({ sandboxes, sandboxId });
try {
  const runner = new Anthropic().beta.messages.toolRunner({
    model: "claude-opus-5-5",
    max_tokens: 16000,
    tools: [browser],
    messages: [{ role: "user", content: "What does pethost.dev/sandboxes say a sandbox costs an hour?" }],
  });
  for await (const message of runner) console.log(message.content);
} finally {
  await browser.close(); // disconnects; Chrome and its tabs stay as they are
}
```

`connect` makes a browser link (`createLink({ sandboxId, browser: {} })`), valid for a minute,
and Playwright connects to it over the Chrome DevTools Protocol, starting the desktop and Chrome
if they do not run (some seconds), with `noDefaults`, so the shared Chrome keeps its own settings.
A connection that drops is made again, with a new link, at the next call, and the tabs keep their
ids: revoking the sandbox's tokens (`revokeTokens` of `updateSandbox`) ends the connection, not
the driver, and `close()` ends the driver. Claude reads a page as its accessibility tree
(`read_page`, from Playwright's aria snapshot) and acts on its elements by the refs the tree gives
(`[ref=e5]`, good while the element is on the page) or on points of a screenshot of the viewport.
A member acts on the tab its `tab_id` names, which it brings to the front and makes the active
tab, else on the active tab.

Served: `navigate`, `screenshot`, `zoom`, the clicks, `hover`, `left_click_drag`,
`left_mouse_down`, `left_mouse_up`, `mouse_move`, `scroll`, `scroll_to`, `type`, `key`,
`hold_key`, `form_input`, `read_page`, `get_page_text`, `wait`, `new_tab`, `list_tabs`,
`switch_tab` and `close_tab`; and, off unless `configs` turns them on, `read_console`,
`read_network` and `javascript_exec` (which the Anthropic SDK lets on only with a `confirm`).
Not served: `find`, which needs a model to match words to elements, and `file_upload`, as the
browser is not on the machine your files are.

`navigate` opens http and https addresses; one without a scheme opens as https, and the sandbox's
own `localhost` as http, as Chrome reads a typed address. Pass a `urlPolicy` to check the addresses
Claude asks for; the sandbox's egress allow-list (`settings.egress` of `createSandbox` or
`updateSandbox`) holds for every request the browser makes, a page's own included.

## OpenAI's computer toolset

```ts
import OpenAI from "openai";
import { ComputerToolset } from "openai/helpers/computer";
import { OpenAIComputer } from "pethost-toolsets/openai/computer";

const toolset = new ComputerToolset(new OpenAIComputer({ sandboxes, sandboxId }));
const response = await toolset.run(
  new OpenAI(),
  { model: "gpt-6.2-sol", input: "Open Chrome, go to pethost.dev and tell me the page's heading." },
  { maxSteps: 50 },
);
console.log(response.output_text);
```

Each action of a batch the model sends is one call to the sandbox, and the screenshot after the
batch is the whole screen, unscaled, so the model's points are the screen's pixels. The sandbox
reads OpenAI's key names (`CTRL`, `ENTER`, `ARROWLEFT`) as they are, keys held with a click, a
drag or a scroll are held, and a letter pressed with other keys is the key (`["CTRL", "A"]` is
ctrl+a, not ctrl+shift+a); its pixels of scrolling become wheel clicks, about 100 pixels a click,
and `wait` waits a second. A move with keys held, which the desktop has no action for, and an
action the sandbox refuses throw `DesktopRefusedError` with its words and its `failure` to branch
on, which ends the run: the computer tool answers the model with a screenshot alone.
`OpenAIComputer` holds nothing to close.

## OpenAI's browser toolset

```ts
import { BrowserToolset } from "openai/helpers/browser";
import { ResponsesToolRunner } from "openai/helpers/responses-tool-runner";
import { OpenAIBrowser } from "pethost-toolsets/openai/browser";

const browser = await OpenAIBrowser.connect({ sandboxes, sandboxId });
const toolset = new BrowserToolset(browser, {
  confirm: () => true, // asked before every member that changes the page
  urlPolicy: (_, url) => url.startsWith("https://pethost.dev/"),
});
try {
  const response = await new ResponsesToolRunner({ browser: toolset }).run(
    new OpenAI(),
    { model: "gpt-6.2-astra", input: "What does pethost.dev/sandboxes say a sandbox costs an hour?" },
    { maxSteps: 40 },
  );
  console.log(response.output_text);
} finally {
  toolset.close();
  await browser.close(); // disconnects; Chrome and its tabs stay as they are
}
```

`connect` reaches the sandbox's Chrome as `ClaudeBrowser` does, and the model reads a page as its
accessibility tree and acts on its elements by their refs. Served: `navigate`, `read_page`,
`get_page_text`, `click`, `type`, `key`, `scroll` (`amount` in pixels; 0 is most of the viewport),
`scroll_to`, `wait_for`, `select_option`, `hover`, `screenshot`, `zoom`, `new_tab`, `switch_tab`,
`close_tab` and `list_tabs`; and, when `additionalMembers` names them, `click_at`, `hover_at`,
`drag_path`, `hold_keys`, `set_checked`, `read_diagnostics` and `run_script`. Not served: `find`,
which needs a model, `read_page_scoped`, and the file members, as the browser is not on the
machine the files are. A member's result says what happened meanwhile, a dialog dismissed or a tab
a page opened; a refusal reaches the model as a `BrowserError`, in the page's or the sandbox's
words.

## OpenAI's computer use by code

```ts
import { ResponsesToolRunner } from "openai/helpers/responses-tool-runner";
import { OpenAICode } from "pethost-toolsets/openai/code";

const code = new OpenAICode({ sandboxes, sandboxId });
try {
  const response = await new ResponsesToolRunner({ functions: code.functions }).run(
    new OpenAI(),
    { model: "gpt-6-astra", input: "Open pethost.dev in the browser and tell me the page's heading." },
    { maxSteps: 50 },
  );
  console.log(response.output_text);
} finally {
  await code.close(); // stops the sessions; the desktop and Chrome run on
}
```

OpenAI's guide recommends computer use by code for GPT-6 Astra: the model writes Python, which
drives the desktop with PyAutoGUI, or JavaScript, which drives the desktop's Chrome with
Playwright, as the tools `exec_py` and `exec_js`. Our base has the runtime for them,
`pethost-code`, and `OpenAICode` hands the model the two tools and runs each call there: one
RunCommand, a GetCommand for each 45 s more the code takes, and a ReadFile for each image it
displayed. Each language is a session that keeps its variables from one call to the next, until
`close()` or the sandbox stops (a pause keeps it); name it with `session` to take it up again.
The output is what the code printed, logged and displayed, an error's stack, or the runtime's
words when it could not run the code; `timeoutSeconds` bounds one call's code (120 s, 600 at
most).

## Links are credentials

A browser link is a credential for the whole browser and every site it is signed in to; a
desktop link and the sandbox's connection token are credentials too. The drivers never put one in
a tool result, an error or a log line: a link lives in the call that makes it, and an error of
Playwright's, which names the address it connected to, is reported with the token cut out. Keep
them out of your own logs as well, and give a person the sandbox's `panelUrl` rather than a link.

A template saved from a sandbox carries its browser's profile, the sites it is signed in to
included, to every sandbox started from it.

## Working on it

```sh
cd typescript
npm install
npm run check      # the package and the examples, TypeScript strict
npm run build      # dist/
```

`examples/` holds a program for each driver: Claude's tool runner with `ClaudeComputer` and with
`ClaudeBrowser`, and OpenAI's with `OpenAIComputer`, `OpenAIBrowser` and `OpenAICode`.

Adapted in part from Anthropic's example browser driver, in
[claude-quickstarts](https://github.com/anthropics/claude-quickstarts) (`browser-toolset`, MIT
License, Copyright (c) 2023 Anthropic): `LICENSE` holds its notice beside ours.

## App Platform: Docker Compose hosting at one flat price

Pethost has two products, sold apart. The App Platform is managed hosting for Docker Compose
projects. A plan has a set size in CPU, memory and disk, at one flat price, for as many projects
as fit. Pethost's software deploys them, gives them HTTPS addresses, keeps their request logs and
backs them up every night. You run it through your agent or from a web panel: both show the same
projects, logs and requests.

- **Always on:** no cold starts, nothing sleeps, on every plan. Security updates install
  themselves.
- **HTTPS addresses:** anything.yourname.pethost.app at once, or your own domain with one DNS
  record. Certificates renew themselves. A password page in front of the whole site: one
  sentence to your agent.
- **Deploys from GitHub:** every push deploys itself, and an earlier commit is one step back.
- **Request logs:** every request with its status and time, the busiest paths and the error
  rate, kept for 30 days.
- **Nightly backups:** encrypted, stored off the machine, kept for 14 days.
- **SSH and SFTP** into any container, and a terminal in the panel.
- **Docker Compose, as written:** a project is a Compose file, and the same file runs anywhere
  else Docker does. A database is one click, Postgres, MariaDB or Valkey, with a page for
  connecting your apps, at no extra cost.
- **In the EU:** your data lives on your machine, and requests to your sites go straight to
  it, never through our panel.

**Pricing.** Starter is €9.99 a month for 2 vCPU, 3 GB of memory and 30 GB of SSD. Grow is
€17.99 for 4 vCPU, 6 GB and 60 GB. Scale is €59.99 for 8 vCPU, 30 GB and 200 GB. Prices are without
VAT. Whatever the plan, you can try anything: as many projects, containers and databases as
fit, nothing metered, and nothing billed on top. The App Platform has no free tier.
[See the plans](https://pethost.dev/#pricing).

**Who it is for.** Solo developers and early startups who host several projects, bots or small
apps and want one fixed monthly bill, and people who build with an AI agent and want it to
deploy and run what it wrote. It is not for large teams whose applications need several regions
or autoscaling: a plan's size is the limit.

## Agent Sandboxes: cloud VMs for AI agents, paused while they think

Pethost Agent Sandboxes are Firecracker microVMs for AI agents, each with its own kernel and root
inside. A sandbox starts in about 0.15 s, pauses with its memory and processes while the agent
thinks, and wakes in 0.1 s at the next call. Commands, files, SSH, a desktop with Chrome, Claude
Code and Codex installed, templates, an egress allow-list and API keys the sandbox never
holds. In the EU.

- **A VM per sandbox:** every sandbox is its own Firecracker microVM with its own Linux kernel,
  root inside.
- **Billed by the second** at its size's price: 2 vCPU, 4 GiB and 10 GiB for $0.018 an hour;
  each run rounded up to a second, 10 s at least.
- **Paused while idle:** it keeps its memory and processes at 30% of the running price, and the
  next call wakes it in about 0.1 s, exactly where it was. Idle longer, it stops: its disk goes to
  object storage at $0.03 per GiB a month of its own data. Nothing is deleted unless a timer says
  so.
- **Starts are free and unlimited:** creating and starting a stopped sandbox cost nothing, and no
  plan counts them; one limit against abuse, 300 a minute, is the same for every workspace.
- **API keys never enter a sandbox:** it sees a placeholder, and the egress proxy puts the key in
  HTTPS request headers, only to the hosts named. An egress allow-list by domain, wildcard, IP or
  CIDR; DNS answers only allowed names.

**Pricing.** Plans from $20 a month without VAT, the price being usage it includes; a balance
pays past it. A free trial: 7 days with $1 of usage. [See Agent Sandboxes](https://pethost.dev/sandboxes/).

**Who it is for.** Companies and developers who build on agents: AI products that run the code
their model writes, coding-agent tools, RL and eval teams, people who run Claude Code or Codex in
the cloud.

## How the App Platform compares

| If you use | The difference |
|---|---|
| [Heroku](https://pethost.dev/about/#heroku), [Render](https://pethost.dev/about/#render), [DigitalOcean App Platform](https://pethost.dev/about/#digitalocean) | There each app, worker and database is one more line on the bill. On Pethost one flat price covers everything you run: as many projects and databases as fit, and nothing sleeps. |
| [Railway, Fly.io](https://pethost.dev/about/#railway), [Koyeb](https://pethost.dev/about/#koyeb) | There CPU, memory and traffic are metered, so the bill moves with every busy month. On Pethost your plan's size is the limit: nothing is metered, nothing is billed on top. |
| [Vercel, Netlify](https://pethost.dev/about/#vercel) | Made for front ends and serverless functions: a bot, a long-running worker or a database is another service with its own price. Pethost runs the front end, the back end and the database side by side, at one flat price. |
| [Coolify, Dokploy](https://pethost.dev/about/#coolify), [CapRover, Dokku, Easypanel](https://pethost.dev/about/#caprover) | Self-hosted: the server is yours to rent, update, secure and back up. On Pethost the server and the panel come together, both looked after for you, and agents are first-class users, not an add-on. |
| [Sliplane](https://pethost.dev/about/#sliplane) | The closest: a flat price per server. There a Compose file is converted into its own services; Pethost runs a Compose project as written. |
| [Replit](https://pethost.dev/about/#replit) | You build and publish inside Replit, with its own agent. Pethost works with the agent you already use, and one flat price covers all your apps. |
| [PythonAnywhere](https://pethost.dev/about/#pythonanywhere) | Python only, no Docker. Pethost runs anything Docker runs, in any language. |
| [A VPS you set up yourself](https://pethost.dev/about/#vps) | The server is the cheap part. You still set up the proxy, DNS, certificates, backups and updates yourself, and fix them when they break. On Pethost all of that is done. |

[About Pethost](https://pethost.dev/about/) has each comparison in full, with prices.

## Questions

**Which AI agents does Pethost work with?**
Almost any agent that supports skills and MCP. The ones we tested ourselves: Claude Code, Codex,
Cursor, ChatGPT, Gemini CLI, OpenClaw, Hermes and Pi.

**What can I deploy?**
Anything that runs in Docker: web apps, APIs, bots, workers, databases. No Dockerfile? With the
plugin installed, your agent knows the details and writes it for you.

**Do I need an agent?**
No. The web panel does the same, and shows the same projects, logs and requests.

**Can I use my own domain?**
Yes. One DNS record, and the certificate comes by itself.

**Is there a free tier?**
No: App Platform plans start at €9.99 a month, and nothing sleeps. Agent Sandboxes has a free
trial of 7 days with $1 of usage. Cancel any time:
[refunds and cancellation](https://pethost.dev/refunds/) has the rules.

