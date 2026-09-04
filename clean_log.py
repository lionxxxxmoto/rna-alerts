"""
One-time cleanup: removes review/editorial/news/etc. articles that
were already logged to matches_log.json before the research-article
filter was added to check_journals.py.

Since the log only stores title (not the original RSS category tags),
this matches title patterns -- broader than the live filter's
prefix-only check, since these titles could have "Review:" or similar
anywhere in the string, not just at the start.

Run once via the "Clean up match log" GitHub Actions workflow, or
locally with: python clean_log.py
"""

import json

MATCHES_LOG_FILE = "matches_log.json"

EXCLUDED_TYPES = [
    "review", "editorial", "news", "comment", "perspective",
    "correction", "erratum", "retraction", "correspondence",
    "obituary", "book review", "research highlight", "news & views",
    "in brief", "this week", "letter to the editor", "author correction",
    "podcast", "remembrance", "hagiography", "in science journals",
    "in memoriam",
]

# Journals excluded entirely, regardless of title -- every article
# these publish is a review by definition, so no per-title check can
# catch it (a review's title often doesn't contain the word "review").
EXCLUDED_JOURNALS = [
    "Nature Reviews Genetics",
    "Nature Reviews Molecular Cell Biology",
]


def is_likely_non_research(entry):
    if entry.get("journal") in EXCLUDED_JOURNALS:
        return True
    t = entry.get("title", "").lower()
    return any(excluded in t for excluded in EXCLUDED_TYPES)


def main():
    with open(MATCHES_LOG_FILE, "r") as f:
        log = json.load(f)

    kept = []
    removed = []
    for entry in log:
        if is_likely_non_research(entry):
            removed.append(entry)
        else:
            kept.append(entry)

    with open(MATCHES_LOG_FILE, "w") as f:
        json.dump(kept, f, indent=2)

    print(f"Removed {len(removed)} of {len(log)} entries:")
    for e in removed:
        print(f"  - [{e.get('journal')}] {e.get('title')}")
    print(f"\n{len(kept)} entries remain.")


if __name__ == "__main__":
    main()
