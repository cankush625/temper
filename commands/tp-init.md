---
description: Detect this repo's verify commands and write the `## Temper` config block into CLAUDE.md.
---
Bootstrap Temper for this project.

1. Run the detector and read its proposal:
   `temper init --dry-run`   (requires `temper` on PATH; otherwise `<temper-repo>/bin/temper init --dry-run`)
2. Sanity-check the proposed `[project]` / `[commands]` toml. Prefer **credential-free, fast**
   checks in `verify` (lint / validate / compile before slow or integration tests); keep any
   credentialed step (deploy, live plan) OUT of the default gate.
3. Write or update the `## Temper` fenced ```toml block in `CLAUDE.md` — idempotent, and never
   clobber other CLAUDE.md content.
4. Ensure `.temper/` exists with `plans/` and `progress.md`.

Only use targets that actually exist in this repo — do not invent commands. If a verify command
needs services/credentials, note that and pick the cheapest real check that proves the work.
