# Operating Safety Rails

Hard constraints any agent working under Temper must follow. These are safety nets, not
suggestions — when one applies, it overrides convenience, momentum, and autonomous/auto mode.

## Cloud / infrastructure roles by environment

Before any infra or cloud action, determine the **target environment** first, then pick the role:

- **Dev** — use a role with *slightly* more than read-only: enough to do the work, never the
  most-privileged role available.
- **Prod** — **strictly read-only by default.** Do not perform any write / mutating / destructive
  action against production.
- **Prod exception** — a non-read-only action in prod is allowed *only* when **all** hold:
  1. the user **explicitly** asked for it,
  2. it is the **specific, selective task** they named (no broadening), and
  3. the user **approves it at the time** — per task, not once-for-the-session.

  **Auto / autonomous mode does NOT bypass this approval.** If running unattended and a prod
  write is required, **stop and ask** rather than proceed.

**Why:** prevent accidental or unattended mutation of production. Dev is a safe place to act;
prod stays read-only unless deliberately and individually authorized.

**If in doubt** about which environment a target is, treat it as prod (read-only) and ask.
