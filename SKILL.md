---
name: deploy-rankings-agents
description: Deploy or update the Rate My Homepage agents on Omnara, which give every website its own machine and AI agent, have Claude, GPT, Gemini, and Muse judges score its homepage out of 10, and commit the results to this repository. Use when the user asks to deploy, set up, update, run, or remove the rankings agents.
---

# Deploy the rankings agents

You are setting up three Omnara agent profiles from `agents/` in this
repository: `rankings`, the main agent; `rankings-site`, which it launches
once per website; and `rankings-judge`, which each site agent launches four
times, once per AI lab. The goal: the user has watched the main agent rank the
20-site dry run in `seeds/dry-run.txt` and has seen the results on the site.

- Skip anything that's already done, and follow the user's lead on order.
- If a command fails, `npx omnara <command> --help` and
  [docs.omnara.com](https://docs.omnara.com) have the details.
- Stop only where a step says to ask the user. Where a step gives a default,
  use it and say in a line what you picked.
- The commands use the Omnara CLI (`npx omnara`); add `--json` to read IDs.

## 1. Connect to Omnara

Run `npx omnara whoami`. If you aren't logged in, run `npx omnara login`
without piping its output and keep it running until the user approves in the
browser; show them the link and code it prints. Pick the org and project
(`npx omnara whoami --json`, `npx omnara projects list --org <org-id> --json`):
use the only one, the defaults from `npx omnara config`, or the project named
`Default`, and ask only if there's still no clear choice. Save it with
`npx omnara config --org <org-id> --project <project-id>`.

## 2. Choose the repository

The main agent pushes results to a GitHub repository, normally the user's
copy of this one. It must be public, because every new machine downloads
`scripts/rank.py` from it. Default to `git remote get-url origin` and confirm
it with the user. This gives `GITHUB_REPO` as `owner/name`.

## 3. Let the main agent push to it

The main agent pushes with a GitHub integration, so no token ever reaches the
agents that read websites. If `npx omnara integrations list --json` already
has one named `rankings-github` that's `active`, reuse it. Otherwise:

```sh
npx omnara integrations create --name rankings-github --integration-kind github_pr --json
```

Then the user, in the browser:

1. Opens `https://app.omnara.com/projects/<project-id>/integrations/<integration-id>`,
   picks the account that owns the repository, selects **Continue to
   GitHub**, and names the App.
2. Selects **Choose repositories on GitHub**, grants only this repository,
   and selects **Connect integration**.
3. On GitHub, opens the App's settings (**Settings** → **Developer settings**
   → **GitHub Apps** → the App → **Edit**), sets **Permissions & events** →
   **Repository permissions** → **Contents** to **Read and write**, saves,
   and accepts the change on the installation.

Wait until the user says it's done. `GITHUB_INTEGRATION` is `rankings-github`.

## 4. Store a PageSpeed Insights API key

Site agents measure each site with Lighthouse on its own machine. For sites
that block that, they fall back to Google's PageSpeed Insights API, which needs
a free API key. The user creates one in the
[Google Cloud console](https://console.cloud.google.com/apis/credentials)
after enabling the PageSpeed Insights API, and can restrict the key to that
API. If a secret named `rankings-psi-key` exists
(`npx omnara secrets list --owner-kind project --owner-project-id <project-id> --name rankings-psi-key --json`),
reuse it. Otherwise get the key from the user and create it:

```sh
npx omnara secrets create --owner-kind project --owner-project-id <project-id> \
  --name rankings-psi-key --material-kind generic --material-value "$PSI_API_KEY" --json
```

Its `id` (`sec_…`) is `PSI_SECRET_ID`.

Then set up X, which the agents use to read replies to the launch post and
answer them. The user creates an app in the
[X developer console](https://console.x.com) with read and write access, adds
pay-per-use credit, and sets a monthly spend cap. Store the app's bearer
token, which can only read, the same way in a secret named `rankings-x-read`;
its `id` is `X_READ_SECRET_ID`. The keys that can post never reach Omnara: the user stores
them as GitHub secrets for the reply workflow. X's API only replies to
posts that mention the account it posts as, so the access token must be
for the account that will post the launch post: with the app's consumer key
and secret as `X_API_KEY` and `X_API_SECRET`, the user runs
`python3 scripts/x_authorize.py --env-file <file>` and approves the app
while logged in as that account. `OPENAI_API_KEY` is an OpenAI API key; the
workflow runs each share card through OpenAI's free moderation check and
leaves the card off any reply it flags. Then they type each value at the
prompt:

```sh
for name in X_API_KEY X_API_SECRET X_ACCESS_TOKEN X_ACCESS_SECRET OPENAI_API_KEY; do
  gh secret set "$name" -R <owner/name>
done
```

## 5. Create the memory store

Site agents pass screenshots and finished results through a memory store
named `rankings`. If
`npx omnara memory-stores list --name rankings --json` finds none:

```sh
npx omnara memory-stores create --name rankings --agent-access read_write --json
```

## 6. Pick the machine pool and models

1. `npx omnara grant pools list --json`: set `MACHINE_POOL` to `default-pool`
   if it's granted, otherwise to the first pool. Its machines need Python and
   Playwright with Chromium, which Omnara-managed pools have.
2. `npx omnara grant models list --json` lists models as `provider_config`
   and `name`. All of them come from one `MODEL_PROVIDER_CONFIG`, normally
   `omnara-openrouter`. Pick:
   - `MODEL_NAME` for the main and site agents: a cheap model that's
     reliable with tools, such as `openai/gpt-6-luna`.
   - `CLAUDE_MODEL`, `GPT_MODEL`, `GEMINI_MODEL`, and `MUSE_MODEL` for the
     judges: the cheapest model from each lab that accepts images, such as
     `anthropic/claude-haiku-5.5`, `openai/gpt-5-nano`,
     `google/gemini-3.5-flash-lite`, and `meta/muse-glimmer-30b`.

   If a model isn't granted, ask the user whether to add it with
   `npx omnara models create` and `npx omnara grant models add`.

## 7. Create the profiles

Each config refers to the next one down by name, so create them in the order
below. For each file, copy it outside the repository (or to a path git
ignores), replace every `{{PLACEHOLDER}}`, and check that
`grep -n '{{' <file>` prints nothing. Then, if
`npx omnara profiles list --name <profile> --json` finds it, run
`npx omnara profiles update <agent-profile-id> --file <file> --json`;
otherwise `npx omnara profiles create --name <profile> --file <file> --json`.

| File | Profile | Placeholders |
| --- | --- | --- |
| `agents/judge.yaml` | `rankings-judge` | `MODEL_PROVIDER_CONFIG`, `GPT_MODEL` |
| `agents/site.yaml` | `rankings-site` | `MODEL_PROVIDER_CONFIG`, `MODEL_NAME`, and the four judge models |
| `agents/rankings.yaml` | `rankings` | all of them from steps 2 to 6, and `X_READ_SECRET_ID` |

Note the `rankings` profile's `id` and `current_config_id`.

## 8. Start the host and run the dry run

The `rankings` agent runs all the time. Start it with the dry run:

```sh
npx omnara agents launch --profile <rankings-profile-id> --config <current-config-id> \
  --message "Rank seeds/dry-run.txt" --json
```

Share `https://app.omnara.com/projects/<project-id>/agents/<agent-id>` so the
user can watch it start a machine and a site agent for each of the 20 sites,
and each site agent start its four judges. The batch takes a few minutes.
When it's done, run `git pull` and `npm run preview`.

## 9. Answer replies on X

After the user posts the launch post, set `x_post_url` in `site/config.json`
to its URL and `x_handle` to the account that posted it, and commit them. Then have a cron ask the host to check for replies
every minute:

```sh
npx omnara crons create --name rankings-x --target-type agent --target-agent-id <agent-id> \
  --cron "* * * * *" --message-template "Check X for new replies." --json
```

Each new reply that names a website gets ranked and answered with its share
card, usually within a few minutes.

## 10. Wrap up

Tell the user:

- **Rank more sites:** send domains to the same host agent, in the console or
  with `npx omnara agents chat <agent-id>`. It skips sites it already ranked
  unless asked to rerun them.
- **Publish the site:** deploy with `npm run build` and the `dist` folder on
  any static host, and set `site/config.json`.
- **Remove it:** delete the three profiles with
  `npx omnara profiles delete <agent-profile-id>`, then the `rankings` memory
  store, the `rankings-psi-key` and `rankings-x-read` secrets, the
  `rankings-x` cron, and the `rankings-github` integration.
