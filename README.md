# Pethost toolsets

Drivers that let an AI model's own computer and browser tools act on a
[Pethost Agent Sandbox](https://pethost.dev/sandboxes/), a Firecracker microVM with its own kernel
and Chrome on a 1280×800 desktop:

- **Claude's computer toolset** (`computer_toolset_20260801`): its clicks, keys and screenshots on
  the sandbox's desktop;
- **Claude's browser toolset** (`browser_toolset_20260801`): its tabs, page reads and form
  inputs in the sandbox's Chrome, through Playwright;
- **OpenAI's computer toolset** (the openai SDK's `ComputerToolset`): the computer tool's actions
  on the sandbox's desktop;
- **OpenAI's browser toolset** (its `BrowserToolset`): page reads and actions by ref in the
  sandbox's Chrome, through Playwright;
- **OpenAI's computer use by code** (`exec_py`, `exec_js`): the model's Python, with PyAutoGUI on
  the desktop, and JavaScript, with Playwright on its Chrome, run in the sandbox's code runtime,
  each a session that keeps its variables.

| Language | Package | Directory |
|---|---|---|
| Python | [`pethost-toolsets`](https://pypi.org/project/pethost-toolsets/) on PyPI, imported as `pethost_toolsets` | [`python/`](python/) |
| TypeScript | [`pethost-toolsets`](https://www.npmjs.com/package/pethost-toolsets) on npm, imported as `pethost-toolsets/claude/computer`, `/claude/browser`, `/openai/computer`, `/openai/browser` and `/openai/code` | [`typescript/`](typescript/) |

```sh
pip install 'pethost-toolsets[claude,openai,browser]'
npm install pethost-toolsets @anthropic-ai/sdk openai playwright-core
```

The drivers act on the same desktop and the same Chrome: a person watching the sandbox in the
panel sees what the agent does, and can take over. Each needs a Pethost API token, a sandbox
started from our `base`, and the model provider's key; a driver needs only its provider's SDK, and
a browser driver Playwright. Each language's README has the code, and the docs walk through all of
them: [Claude's and OpenAI's computer use](https://pethost.dev/docs/sandboxes/claude-and-openai/).

## How they behave

- **Every action is one call to the sandbox.** A computer action is one `ControlDesktop`, which
  does it and answers with a screenshot. The browser toolsets drive Chrome through a browser
  link, the Chrome DevTools Protocol of the sandbox's own browser. A run of code is one
  `RunCommand` of `pethost-code`, the runtime in our base.
- **The sandbox's words reach the model.** The drivers check nothing the sandbox checks: a point
  off the screen or a key it does not know comes back as the sandbox's refusal, in its words.
- **Links are credentials.** A browser link opens the whole browser and every site it is signed
  in to. The drivers keep the sandbox's token and every link out of tool results, errors and log
  lines.

These packages are built and released from Pethost's own repository: this one is a copy of it, so
a pull request here is not merged as it is. Issues are welcome here, or at support@pethost.dev.

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

