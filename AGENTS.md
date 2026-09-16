# AGENTS.md — daily-pipeline

> This repo is **public by design** (build in public). Treat everything you
> write here as visible to the world. The first half of this file is the
> owner's standing policy — copy it into any repo you work in.

## Security & privacy (hard rules, apply everywhere)

1. **NEVER commit secrets**: API keys, tokens, passwords, credentials of any
   kind — not in code, configs, workflows, logs, data files, or git history.
2. Secrets live in **GitHub Secrets** (or the deploy platform's env vars) and
   are injected at runtime. Code references placeholders only
   (e.g. `__WEB3FORMS_KEY__`, `process.env.MY_API_KEY`).
3. **NEVER commit personal data**: real names, addresses, family details,
   financial info, or anything identifying the owner. Public-source data only
   (e.g. HN comments, RSS headlines).
4. If a secret is ever committed by accident: **revoke/rotate it first**,
   then purge it from git history, then tell the owner what happened.
5. New data source? Prefer public APIs and RSS over scraping login-walled or
   aggressively anti-bot sites (LinkedIn, Redfin/Zillow, Xiaohongshu official).
   When in doubt, ask before adding the scraper.

## Pipeline conventions (this repo)

- One pipeline = one folder: `scripts/` (collector), `data/` (output JSON),
  plus `.github/workflows/<name>-collect.yml`.
- Workflows: `schedule` cron (stagger the minute off `:00`, GitHub throttles
  round marks) + `workflow_dispatch` for manual runs.
  `permissions: contents: write`; commit results back to `data/`
  (both `latest.json` and `history/<date>.json`).
- Collectors **normalize but don't judge**: no scoring, no dedup against
  history — the consumer (Muse) does that.
- Output schema:
  `{generated_at, run_date (America/Los_Angeles), sources[], count, items[]}`;
  each item: `id, title, url, source, company_or_poster, contact,
  published_at, snippet, categories[], signal, found_date, status`.

## Schedule notes

- GitHub's scheduler is best-effort and can run a few minutes late; never rely
  on exact timing. Consumers should tolerate stale data and fall back gracefully.
- Keep the repo active (a commit at least every 60 days) or GitHub pauses
  scheduled workflows.
