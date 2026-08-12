# Skill-Capability-Router

Route a task to the best installed skill using a **generated capability registry**. Built for environments where a large skill library is managed by a central tool (here: CC Switch + Claude Code) — 846 skills across 20 categories, one thin discovery table.

- [中文说明](README.zh-CN.md)
- `data/thin-table.md` — route here first
- `data/semantic-table.md` — full rows, read after a match
- `data/skills.json` — full machine-readable catalog

## What it is

| Piece | Purpose |
| --- | --- |
| **Router skill** (`skill-capability-router`) | At runtime, reads the registry and routes a task to the exact installed skill. Skill name = its directory, e.g. `xero-automation`. |
| **Generator** (`scripts/generate_router.py`) | Scans the CC Switch skill database and deterministically regenerates the registry. No third-party dependencies. |
| **Published catalog** (`data/`) | Every managed skill: canonical name, display name, category, capability `verb + object`, aliases, source, per-client enablement. |

Duplicates are canonicalized: underscore/hyphen spellings of the same tool collapse to one entry (e.g. `anthropic-administrator-automation` vs `anthropic_administrator-automation`), with the discarded spelling kept as an alias.

## Quick start

### 1. Install the router skill

**CC Switch** — add this repository to the skill repos, then enable `skill-capability-router`. The skill directory is `.claude/skills/skill-capability-router/`.

**Manual** — copy that directory into `~/.claude/skills/` (or the equivalent for your client).

### 2. Use it

Just ask in natural language — *"automate Xero"*, *"send a Slack message"*, *"work on a PDF"*, *"query Snowflake"*, *"pull CRM leads"*. The router skill consults the thin table and invokes the matching installed skill.

### 3. Regenerate when skills change

```bash
python scripts/generate_router.py                     # reads ~/.cc-switch/cc-switch.db
python scripts/generate_router.py --db "C:\path\cc-switch.db"
python scripts/generate_router.py --json data/skills.json   # re-run from the exported catalog
python scripts/generate_router.py --validate-only           # check without writing
```

## Repository layout

```
.claude/skills/skill-capability-router/   the installable router skill (SKILL.md + agents/)
scripts/generate_router.py                deterministic registry generator
scripts/test_router.py                    route-test against natural-language tasks
data/README.md                            generated index: files, categories, how to use
data/skills.json                          full catalog (canonical + aliases + enablement)
data/thin-table.md                        discovery table, grouped by category
data/semantic-table.md                    full per-skill rows
data/manifest.json                        generation metadata + validation report (gitignored)
```

## Categories

`finance-payments` · `crm-sales` · `marketing-email` · `seo-analytics` · `social-media` · `communication-collab` · `project-management` · `hr-recruiting` · `support-helpdesk` · `dev-tools` · `data-databases` · `ai-ml-media` · `documents-files` · `ecommerce-retail` · `travel-events` · `sports-gaming` · `health-fitness` · `logistics-field` · `education` · `general`

The category map is a curated keyword table inside the generator (`CATEGORY_KEYWORDS` + `BASE_OVERRIDES`). Adjust it and regenerate — output is deterministic.

## Notes

- The published catalog reflects the author's skill set and per-client enablement. Regenerate for your own environment.
- **No secrets.** `data/` holds only skill names, descriptions, categories, and enablement flags — no tokens, keys, or paths.
- `scripts/generate_router.py` is dependency-free (stdlib only) and validated (0 errors on 868 source rows → 846 canonical entries). `scripts/test_router.py` runs sample natural-language tasks through the routing logic — `python scripts/test_router.py "query Snowflake"`.

## License

MIT — see [LICENSE](LICENSE).
