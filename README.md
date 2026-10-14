# Rate My Homepage

AI agents score websites on eight things, from page speed to how well AI
agents can use them, and rank them at
[ratemyhomepage.pages.dev](https://ratemyhomepage.pages.dev).

## How it works

Two [Omnara](https://www.omnara.com) agent profiles, in [`agents/`](agents),
do the work:

- **The main agent** ([`rankings.yaml`](agents/rankings.yaml)) takes a batch
  of domains, publishes a "scoring" placeholder for each one, and gives every
  site its own machine and its own site agent. As results come in,
  [`scripts/publish.py`](scripts/publish.py) checks them and pushes them
  here.
- **Site agents** ([`site.yaml`](agents/site.yaml)), one per website, run
  [`scripts/rank.py`](scripts/rank.py) to measure the site with Lighthouse and
  take screenshots in a real browser, ask [Ora](https://ora.ai)'s MCP server for
  the site's agent-readiness score, and review the site. They read untrusted
  web pages, so they hold no credentials.

[RUBRIC.md](RUBRIC.md) defines every score.

## Get ranked

Reply to [@AsherDale13](https://x.com/AsherDale13) on X with your domain.

## Run your own

Open this repository in Claude Code, Codex, Cursor, or another coding agent
and say:

```text
Follow SKILL.md to deploy the rankings agents.
```

It signs you in to Omnara, stores a PageSpeed Insights API key for sites that
block Lighthouse, connects
GitHub so the main agent can push results, creates both profiles, and ranks a
first batch.

## Build the site

```sh
npm run build     # writes dist/
npm run preview   # builds and serves dist/ locally
npm run stats     # shows how scores spread across sites
```

Deploy `dist/` to any static host. Cloudflare Pages and Vercel work with
`npm run build` as the build command and `dist` as the output directory.
Site settings are in [site/config.json](site/config.json).
