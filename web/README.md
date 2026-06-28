# Atemporal ESP Trainer — Web

A zero-build, fully client-side version of the trainer, designed to deploy to
Vercel as a static site.

## How it works

- **No backend, no database.** Trials are stored in the browser's
  `localStorage` under the key `esp_trainer.trials.v1`.
- **Atemporal protocol preserved.** A trial is opened with no target. You lock
  a guess. The target is generated only at reveal time, using
  `crypto.getRandomValues` (unbiased rejection sampling) drawn *after* the
  guess is locked. Nothing exists to peek at while a trial is open.
- **Scoring.** Hit rate and a one-sided binomial p-value `P(X >= hits)` against
  the 10% chance baseline, matching the Python CLI's statistics.

## Run locally

It's plain HTML/CSS/JS — open `web/index.html` directly, or serve the folder:

```bash
cd web
python -m http.server 8000
# visit http://localhost:8000
```

## Deploy to Vercel

The repository root contains a `vercel.json` that serves this `web/` directory
as static output with no build step (`outputDirectory: "web"`, no build
command). Import the repo into Vercel, or deploy from the CLI:

```bash
vercel --prod
```

## Relationship to the CLI

This mirrors the protocol in the root `esp_trainer.py`. The CLI uses SQLite and
a configurable reveal delay; the web version stores data per-browser and
reveals on demand (the integrity comes from deferring target generation, not
from an artificial wait).
