# pethost-toolsets for Python

Drivers that give an AI agent the desktop and the browser of a
[Pethost Agent Sandbox](https://pethost.dev/sandboxes/): a Firecracker microVM with its own
kernel, and Chrome on a 1280×800 desktop.

| Driver | For | Over |
|---|---|---|
| `ClaudeComputer`, `AsyncClaudeComputer` | Claude's computer toolset, `computer_toolset_20260801` | the sandbox's screen: ControlDesktop |
| `ClaudeBrowser`, `AsyncClaudeBrowser` | Claude's browser toolset, `browser_toolset_20260801` | the sandbox's Chrome, through Playwright and a browser link |
| `OpenAIComputer`, `AsyncOpenAIComputer` | the openai SDK's `ComputerToolset`, OpenAI's computer tool | the sandbox's screen: ControlDesktop |
| `OpenAIBrowser`, `AsyncOpenAIBrowser` | the openai SDK's `BrowserToolset` | the sandbox's Chrome, through Playwright and a browser link |
| `OpenAICode`, `AsyncOpenAICode` | OpenAI's computer use by code: `exec_py` and `exec_js` | the sandbox's code runtime, through RunCommand |

All are imported from `pethost_toolsets`. They act on the same desktop and the same Chrome: a
person watching the sandbox's page in the panel sees what the agent does, and the sites Chrome is
signed in to stay signed in, on the sandbox's disk.

Each needs a Pethost API token (`PETHOST_TOKEN`, made in the panel's Settings, under "API
tokens"), a sandbox started from our base, and the model's own key (`ANTHROPIC_API_KEY` or
`OPENAI_API_KEY`). The docs walk through all of them:
[Claude's and OpenAI's computer use](https://pethost.dev/docs/sandboxes/claude-and-openai/).

## Install

Python 3.11 or later, with the extras of the drivers you use:

```sh
pip install 'pethost-toolsets[claude]'           # ClaudeComputer
pip install 'pethost-toolsets[claude,browser]'   # ClaudeBrowser too
pip install 'pethost-toolsets[openai]'           # OpenAIComputer, OpenAICode
pip install 'pethost-toolsets[openai,browser]'   # OpenAIBrowser too
```

It brings the Pethost SDK (`pethost` 0.10, the first with browser links). The extras are what the
drivers need beside it: `[claude]` is `anthropic` 2, `[openai]` is `openai` 3.59 or later, and
`[browser]` is Playwright 1.65 or later. A driver whose extras are missing says which to install
when it is first imported. Playwright only connects to the sandbox's Chrome here, so
`playwright install` is not needed.

## Claude's computer toolset

```python
from anthropic import Anthropic
from pethost.sandboxes import Sandboxes
from pethost_toolsets import ClaudeComputer

with Sandboxes() as sandboxes:  # the token: PETHOST_TOKEN
    sandbox = sandboxes.create_sandbox("base")
    with ClaudeComputer(sandboxes, sandbox.sandbox_id, confirm=lambda context: True) as computer:
        runner = Anthropic().beta.messages.tool_runner(
            model="claude-opus-5-5",
            max_tokens=16000,
            tools=[computer],
            messages=[{"role": "user", "content": "Open Chrome, go to pethost.dev and tell me the page's heading."}],
        )
        for message in runner:
            print(message.content)
```

Every action is one ControlDesktop call. A screenshot is the whole screen, unscaled, which fits
every current model's image limits, so Claude's coordinates are the screen's pixels; a zoom is
that part of the screen scaled up. What the desktop refuses (a point off the screen, a key it
does not know) reaches Claude in the desktop's own words. `confirm` is the Anthropic SDK's: it is
asked before every action, and the SDK requires one while `type`, `key` or `hold_key` is on
(`lambda context: True` runs everything, for a sandbox that holds nothing of yours). With
`AsyncAnthropic`, take `AsyncClaudeComputer` and an `AsyncSandboxes`.

## Claude's browser toolset

```python
from anthropic import Anthropic
from pethost.sandboxes import Sandboxes
from pethost_toolsets import ClaudeBrowser

with Sandboxes() as sandboxes:
    sandbox = sandboxes.create_sandbox("base")
    with ClaudeBrowser.connect(sandboxes, sandbox.sandbox_id) as browser:
        runner = Anthropic().beta.messages.tool_runner(
            model="claude-opus-5-5",
            max_tokens=16000,
            tools=[browser],
            messages=[{"role": "user", "content": "Open pethost.dev/sandboxes and say what a sandbox costs."}],
        )
        for message in runner:
            print(message.content)
```

`connect` makes a browser link (`create_link(browser=BrowserLink())`), starts the desktop when it
does not run (some seconds) and connects Playwright to its Chrome, with `no_defaults`, so the
shared Chrome keeps its own settings. A link the server refuses (a stopped sandbox) raises
`BrowserConnectionError` with the server's words. With `AsyncAnthropic`:
`async with await AsyncClaudeBrowser.connect(async_sandboxes, sandbox_id) as browser:`.

- **Tabs.** Every tab of that Chrome is reported, those a page or a person opens too. A member
  acts on the tab it names, else the active one, and that tab is brought to the front of the
  desktop and becomes the active one.
- **read_page** is Playwright's accessibility snapshot of the page, with a ref for each element
  (`[ref=e5]`) that the clicks, `hover`, `scroll_to` and `form_input` take. A ref holds while its
  element is on the page; a new document's elements get new refs.
- **navigate** opens http and https addresses and `about:blank`. A host with no scheme opens as
  https, and the sandbox's own `localhost` as http, as Chrome reads a typed address.
- **Dialogs** a page opens are dismissed, and Claude is told what they asked.
- **Off:** `find` (it matches a description in words) and `file_upload`. `javascript_exec`,
  `read_console` (the page's console and its uncaught errors) and `read_network` (its requests,
  with their status, type and time) are off unless `configs` turns them on, as the SDK has them,
  and `javascript_exec` takes a `confirm`.
- **A script** of `javascript_exec` is given 30 s for its value. `AsyncClaudeBrowser` gives up on
  any script then; `ClaudeBrowser` gives up on a promise that has not settled, but waits for a
  script that keeps the page busy in a loop, as Playwright's synchronous API cannot give up a call.
  A question the driver asks a page itself (where it is scrolled to, its text) is given 15 s.
- **The link** is a credential for the whole browser and every site it is signed in to. The
  driver hands it to Playwright alone, makes it open connections for 60 s only (the connection
  lasts past it), and keeps its token out of every text it makes.
- **A connection that drops** (the sandbox's server restarted, `revoke_tokens`) is made again,
  with a new link, at the next call, and the tabs keep their ids. `close()` ends the driver: it
  disconnects, and Chrome goes on running in the sandbox.
- **A connection is a session:** the sandbox does not pause while it is open, so close the
  toolset when the work is done.
- One browser a sandbox: for several at once, use several sandboxes.

## OpenAI's computer toolset

```python
from openai import ComputerToolset, OpenAI
from pethost.sandboxes import Sandboxes
from pethost_toolsets import OpenAIComputer

with Sandboxes() as sandboxes:
    sandbox = sandboxes.create_sandbox("base")
    toolset = ComputerToolset(OpenAIComputer(sandboxes, sandbox.sandbox_id))
    response = toolset.run(
        OpenAI(),
        {"model": "gpt-6.2-sol", "input": "Open Chrome, go to pethost.dev and tell me the page's heading."},
        max_steps=50,
    )
    print(response.output_text)
```

Every action of a batch the model sends is one ControlDesktop call, and the screenshot after the
batch is the whole screen, unscaled, so the model's points are the screen's pixels. Key names go
to the desktop as OpenAI writes them (`CTRL`, `ENTER`, `ARROWLEFT`), joined by `+`, and keys held
with a click, a drag or a scroll are held; a scroll is in wheel clicks of about 100 pixels; a wait
is 1 s. A move with keys held, which the desktop has no action for, raises `ValueError`, and an
action the desktop refuses raises `DesktopRefusedError`, with the desktop's `failure` to branch
on: the computer tool answers the model with a screenshot alone, so the run ends there.
`OpenAIComputer` holds nothing to close. With asyncio, take `AsyncOpenAIComputer`, an
`AsyncSandboxes` and `AsyncComputerToolset`.

## OpenAI's browser toolset

```python
from openai import OpenAI
from openai.lib.browser import BrowserToolset
from openai.lib.responses_tool_runner import ResponsesToolRunner
from pethost.sandboxes import Sandboxes
from pethost_toolsets import OpenAIBrowser

with Sandboxes() as sandboxes:
    sandbox = sandboxes.create_sandbox("base")
    with OpenAIBrowser.connect(sandboxes, sandbox.sandbox_id) as browser:
        toolset = BrowserToolset(
            browser,
            confirm=lambda context: True,  # asked before every member that changes the page
            url_policy=lambda context, url: url.startswith("https://pethost.dev/"),
        )
        response = ResponsesToolRunner(browser=toolset).run(
            OpenAI(),
            {"model": "gpt-6.2-astra", "input": "Open pethost.dev/sandboxes and say what a sandbox costs."},
            max_steps=40,
        )
        print(response.output_text)
```

`connect` reaches the sandbox's Chrome as `ClaudeBrowser` does, and `close()` disconnects and
leaves Chrome running. `read_page` is Playwright's snapshot of the page; its refs (`e5`, `f1e2`)
are what `click`, `type`, `select_option`, `hover`, `scroll_to` and `set_checked` take. Served:
`navigate`, `read_page`, `get_page_text`, `click`, `type`, `key`, `scroll` (`amount` in pixels; 0
is most of the viewport), `scroll_to`, `wait_for`, `select_option`, `hover`, `screenshot`, `zoom`,
`new_tab`, `switch_tab`, `close_tab` and `list_tabs`; and, when `additional_members` names them,
`click_at`, `hover_at`, `drag_path`, `hold_keys`, `set_checked`, `read_diagnostics` and
`run_script`. Not served: `find`, which needs a model, `read_page_scoped`, and the file members,
as the files are not where the browser is. A member's result says what happened meanwhile, a
dialog dismissed or a tab a page opened, and a refusal reaches the model as a `BrowserError`, in
the page's or the sandbox's words. With asyncio: `async with await AsyncOpenAIBrowser.connect(...)`
and `AsyncBrowserToolset`.

## OpenAI's computer use by code

```python
from openai import OpenAI
from openai.lib.responses_tool_runner import ResponsesToolRunner
from pethost.sandboxes import Sandboxes
from pethost_toolsets import OpenAICode

with Sandboxes() as sandboxes:
    sandbox = sandboxes.create_sandbox("base")
    with OpenAICode(sandboxes, sandbox.sandbox_id) as code:
        response = ResponsesToolRunner(functions=code.functions).run(
            OpenAI(),
            {"model": "gpt-6-astra", "input": "Open pethost.dev in the browser and tell me the page's heading."},
            max_steps=50,
        )
        print(response.output_text)
```

OpenAI's guide recommends computer use by code for GPT-6 Astra: the model writes Python, which
drives the desktop with PyAutoGUI, or JavaScript, which drives the desktop's Chrome with
Playwright, as the tools `exec_py` and `exec_js`. Our base has the runtime for them,
`pethost-code`, and `OpenAICode` hands the model the two tools and runs each call there: one
RunCommand, a GetCommand for each 45 s more the code takes, and a ReadFile for each image it
displayed. Each language is a session that keeps its variables from one call to the next, until
`close()` or the sandbox stops (a pause keeps it); name it with `session` to take it up again.
The output is what the code printed, logged and displayed, an error's traceback, or the runtime's
words when it could not run the code; `timeout_seconds` bounds one call's code (120 s, 600 at
most). With asyncio, take `AsyncOpenAICode` and `AsyncResponsesToolRunner`.

## Examples

`examples/` has a program for each driver, which starts a sandbox, gives the model the task on
its command line and deletes the sandbox at the end: `claude_computer.py`, `claude_browser.py`,
`openai_computer.py`, `openai_browser.py` and `openai_code.py`.

## Checks

```sh
cd python
pip install -e '.[claude,openai,browser]' pyright mypy
pyright && mypy        # both strict, over the package and examples/
```

Thanks to Anthropic's example browser driver (claude-quickstarts, `browser-toolset`, MIT License),
whose reading of a page's text this driver follows.

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
€17.99 for 4 vCPU, 6 GB and 60 GB. Scale is €59 for 8 vCPU, 30 GB and 200 GB. Prices are without
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

