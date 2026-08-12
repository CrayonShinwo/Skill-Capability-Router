#!/usr/bin/env python3
"""
Route-test the Skill-Capability-Router against natural-language tasks.

Loads the generated catalog (data/skills.json) and, for each task, scores every
installed skill on three signals:

  1. tool-name match  — the skill's base / first base segment / object appears
                       as a whole word in the task (strongest)
  2. category match   — the task hits the skill's category's keywords
  3. description match — task words appear in the skill's description (fallback,
                       catches "transcribe", "OCR", "IP address" tasks that do
                       not name a specific tool)

Prints the top candidates per task and marks pure capability matches, so a
"no exact tool installed" case surfaces the closest skills instead of a guess.

Usage
-----
  python scripts/test_router.py                 # run the built-in sample tasks
  python scripts/test_router.py "query Snowflake"  # test a single free-text task
"""

from __future__ import annotations

import json
import os
import re
import sys

from generate_router import CATEGORY_KEYWORDS, CATEGORY_ORDER, DOMAIN_WORD_FALLBACK

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAMPLE_TASKS = [
    "automate Xero invoicing and reconciliation",
    "convert this PDF into plain text",
    "run a query on Snowflake for last month sales",
    "pull new leads from Salesforce",
    "log my hours in Toggl",
    "create a candidate profile in Ashby",
    "track a shipment in ShipEngine",
    "sync Zoho Books transactions with the bank",
    "transcribe this meeting recording",
    "OCR this scanned invoice",
    "send a campaign via Mailchimp",
    "send a message on Slack",
    "query the Postgres database for users",
    "look up the IP address of this host",
    "push a notification via Twilio SMS",
    "generate a hero image for the landing page",
    "send an email with Resend",
    "plan an event and sell tickets on Eventbrite",
]


STOPWORDS = {
    "a", "an", "the", "this", "that", "with", "for", "and", "via", "from",
    "into", "on", "to", "of", "in", "at", "by", "up", "out", "as", "is", "are",
    "it", "its", "my", "your", "our", "me", "i", "we", "they", "he", "she",
    "do", "does", "did", "am", "be", "been", "was", "were",
}
# verbs are capability signals for description/category matching but must not
# drive tool-name matching (a base is a proper noun, never a verb)
VERBS = {
    "automate", "send", "create", "query", "run", "generate", "plan", "track",
    "log", "pull", "sync", "reply", "push", "convert", "use", "work", "book",
    "sell", "build", "make", "set", "get", "fetch", "list", "update", "delete",
    "read", "write", "post", "share", "schedule", "transcribe", "extract",
    "lookup", "manage", "handle", "help", "deploy", "start", "stop", "add",
    "edit", "search", "find", "analyze", "review", "open", "close", "download",
    "upload", "create", "publish",
}


def tokenize(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def category_task_score(task_low: str) -> dict[str, int]:
    """Score how strongly a task matches each category's keyword list.

    Hyphens are normalized to spaces so ``landing-page`` matches
    ``landing page`` in the task.
    """
    low = task_low.replace("-", " ")
    scores = {cat: 0 for cat in CATEGORY_ORDER}
    for cat in CATEGORY_ORDER:
        if cat == "general":
            continue
        for kw in CATEGORY_KEYWORDS.get(cat, ()):
            k = kw.replace("-", " ")
            if len(kw) >= 4 and k in low:
                scores[cat] += min(len(kw), 12)
        for w, cat2 in DOMAIN_WORD_FALLBACK:
            if cat2 == cat and w in low:
                scores[cat] += 6
    return scores


def load_catalog() -> list[dict]:
    with open(os.path.join(ROOT, "data", "skills.json"), encoding="utf-8") as f:
        return json.load(f)


def route(catalog: list[dict], task: str, top: int = 3) -> list[tuple[int, dict]]:
    low = task.lower().replace("-", " ")
    content = set(tokenize(low)) - STOPWORDS
    tool_words = content - VERBS
    cat_scores = category_task_score(low)
    best_cat = max(cat_scores, key=lambda c: cat_scores[c])

    scored: list[tuple[int, int, dict]] = []        # (total, tool_score, skill)
    for e in catalog:
        base_sp = re.sub(r"[^a-z0-9 ]", " ", e["base"]).strip()
        tool = 0
        if base_sp and re.search(rf"(?<![a-z0-9]){re.escape(base_sp)}(?![a-z0-9])", low):
            tool = 100 + len(tokenize(base_sp))     # exact tool name, longer = more specific
        else:
            btok = tokenize(e["base"])
            otok = tokenize(e["object"])
            if btok and btok[0] in tool_words:
                tool = 70 + len(btok)               # first base segment ("salesforce" -> salesforce-*-cloud)
            elif otok and otok[0] in tool_words:
                tool = 55 + len(otok)               # object word
            else:
                hit = max((len(w) for w in tool_words if len(w) >= 3 and w in e["base"]), default=0)
                if hit:
                    tool = hit                      # weak base substring (e.g. "ip" tools)
        score = tool + cat_scores.get(e["category"], 0)
        dl = e["description"].lower()
        score += sum(2 for w in content if len(w) >= 4 and w in dl)
        # for pure-capability matches, prefer skills in the task's own category
        if tool == 0:
            score += 8 if e["category"] == best_cat else -15
        if score:
            scored.append((score, tool, e))

    scored.sort(key=lambda x: (-x[0], x[2]["name"]))
    seen, out = set(), []
    for _, tool, e in scored:
        if e["base"] in seen:
            continue
        seen.add(e["base"])
        out.append((tool, e))
        if len(out) >= top:
            break
    return out


def main() -> int:
    catalog = load_catalog()
    tasks = sys.argv[1:] if len(sys.argv) > 1 else SAMPLE_TASKS
    print(f"catalog: {len(catalog)} skills\n")
    for task in tasks:
        hits = route(catalog, task)
        if not hits:
            print(f"  [--]  {task}")
            print(f"        -> no installed skill matched")
            continue
        lines = []
        for tool, e in hits:
            mark = "[exact]" if tool >= 70 else "[similar]"
            lines.append(f"        {mark} {e['name']:26s} [{e['category']}] {e['verb']} {e['object']}")
        print(f"  [OK]  {task}")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
