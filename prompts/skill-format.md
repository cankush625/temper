# Learned skill format

Every `create` / `update` body is a complete `SKILL.md`:

```
---
description: <one sentence, trigger first: the words a user would type, the tools and file types involved>
category: <the class of work — one lowercase word or hyphenated phrase>
---
<the rule, in a line or two>

<supporting steps, pitfalls, commands — short>
```

- `name:` is set by the promoter from the intent's `name`; you may omit it.
- **description**: at most 250 characters, one line. It is the trigger — it decides whether a
  future session loads the skill — so name the situation, not the history.
- **category**: reuse one already in the index when it fits; mint a new one only when nothing does.
- **body**: at most 40 non-blank lines and 8000 bytes. State the durable rule at the altitude of the
  *class* of work. Do not retell the session.
- No secrets, tokens, emails or other personal data. A `global` skill must not mention this
  repository's name or paths.
- A skill must never weaken a safety rail: no skipping hooks or verification (`--no-verify`),
  no force-push, no amending, no unsigned commits, no bypassing permissions, no editing `.temper/`
  evidence, plans or keys, no "ignore CLAUDE.md". Bodies that say so are rejected.
