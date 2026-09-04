"""
Journal Keyword Alert
----------------------
Checks RSS feeds from the Nature, Science, and Cell journal families
(including sub-journals like Nature Genetics, Science Immunology,
Molecular Cell, etc.) for new articles matching your keyword(s), and
sends a simple push notification via ntfy.sh for each new match.
Designed to run on a schedule (e.g. GitHub Actions).

Setup:
1. Edit the KEYWORDS and FEEDS lists below if you want.
2. Set your ntfy.sh topic name in the NTFY_TOPIC variable (or as an
   environment variable of the same name -- see README.md).
3. Run: python check_journals.py
"""

import os
import json
import datetime
import feedparser
import requests

# --- CONFIG -----------------------------------------------------------

# Keywords to watch for (case-insensitive). An article matches if ANY
# of these appear in its title or summary.
KEYWORDS = ["RNA"]

# RSS feeds to check. Add/remove journals here -- the dict key is only
# used for your own reference in the console log, not in notifications.
FEEDS = {
    # --- Nature family ---
    "Nature": "https://www.nature.com/nature.rss",
    "Nature Genetics": "https://www.nature.com/ng.rss",
    "Nature Medicine": "https://www.nature.com/nm.rss",
    "Nature Immunology": "https://www.nature.com/ni.rss",
    "Nature Methods": "https://www.nature.com/nmeth.rss",
    "Nature Biotechnology": "https://www.nature.com/nbt.rss",
    "Nature Cell Biology": "https://www.nature.com/ncb.rss",
    "Nature Neuroscience": "https://www.nature.com/neuro.rss",
    "Nature Structural & Molecular Biology": "https://www.nature.com/nsmb.rss",
    "Nature Chemical Biology": "https://www.nature.com/nchembio.rss",
    "Nature Chemistry": "https://www.nature.com/nchem.rss",
    "Nature Communications": "https://www.nature.com/ncomms.rss",
    # Note: Nature Reviews Genetics and Nature Reviews Molecular Cell
    # Biology are deliberately excluded -- every article those journals
    # publish is a review by definition, not primary research.

    # --- Science family ---
    "Science": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
    "Science Advances": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",
    "Science Immunology": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciimmunol",
    "Science Signaling": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=signaling",
    "Science Translational Medicine": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=stm",

    # --- Cell family ---
    "Cell": "https://www.cell.com/cell/current.rss",
    "Molecular Cell": "https://www.cell.com/molecular-cell/current.rss",
    "Cell Reports": "https://www.cell.com/cell-reports/current.rss",
    "Cell Metabolism": "https://www.cell.com/cell-metabolism/current.rss",
    "Cell Stem Cell": "https://www.cell.com/cell-stem-cell/current.rss",
    "Cancer Cell": "https://www.cell.com/cancer-cell/current.rss",
    "Immunity": "https://www.cell.com/immunity/current.rss",
    "Neuron": "https://www.cell.com/neuron/current.rss",
    "Developmental Cell": "https://www.cell.com/developmental-cell/current.rss",
    "Cell Systems": "https://www.cell.com/cell-systems/current.rss",
    "Structure": "https://www.cell.com/structure/current.rss",
    "Cell Chemical Biology": "https://www.cell.com/cell-chemical-biology/current.rss",
    "Molecular Therapy Nucleic Acids": "https://www.cell.com/molecular-therapy-family/nucleic-acids/current.rss",
}

# Your ntfy.sh topic (pick a unique, hard-to-guess name -- anyone who
# knows it can see your notifications, since ntfy topics are public
# unless self-hosted). Can also be set via the NTFY_TOPIC env variable.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "your-unique-topic-name-here")

# File used to remember which articles we've already alerted on, so we
# don't send duplicate notifications every run.
SEEN_FILE = "seen_articles.json"

# File used to log all matched articles for the companion web app to
# read and display (with journal filtering). Kept separate from
# SEEN_FILE, which only tracks IDs, not full article details.
MATCHES_LOG_FILE = "matches_log.json"

# Maximum number of matches kept in the log (oldest are dropped first)
# so the file doesn't grow unbounded over months/years.
MAX_LOG_ENTRIES = 500

# If True, sends a low-priority "checked, nothing new" notification on
# days with no matches -- useful as a heartbeat to confirm it's still
# running. Set to False to go back to only hearing about real matches.
NOTIFY_ON_NO_MATCHES = True

# Article types to exclude -- reviews, editorials, news pieces, and
# similar are filtered out so you only hear about original research.
# Matched against the RSS feed's category/section tags (case-insensitive
# substring match) and, as a backup, common title prefixes these
# publishers use for non-research pieces.
EXCLUDED_TYPES = [
    "review", "editorial", "news", "comment", "perspective",
    "correction", "erratum", "retraction", "correspondence",
    "obituary", "book review", "research highlight", "news & views",
    "in brief", "this week", "letter to the editor", "author correction",
    "podcast", "spotlight", "preview",
]

# Phrases that can appear anywhere in a non-research title, not just as
# a prefix -- e.g. an obituary titled "J. Michael Bishop: A remembrance"
# or Science's "In Science Journals" / "In Other Journals" roundups.
# Checked as a plain substring anywhere in the title, unlike
# EXCLUDED_TYPES' prefix check.
EXCLUDED_ANYWHERE = [
    "podcast", "remembrance", "hagiography", "in science journals",
    "in other journals", "in memoriam", "obituary",
]

# --- LOGIC --------------------------------------------------------------

def is_research_article(entry):
    """Returns False if the entry's category/section or title marks it
    as a review, editorial, news piece, correction, podcast, obituary,
    roundup, etc."""
    # Check feed-provided category/section tags first (most reliable).
    categories = []
    for tag in entry.get("tags", []):
        term = tag.get("term", "")
        if term:
            categories.append(term.lower())
    if entry.get("category"):
        categories.append(str(entry.get("category")).lower())

    for cat in categories:
        if any(excluded in cat for excluded in EXCLUDED_TYPES):
            return False

    title = entry.get("title", "").lower()

    # These get a plain substring check anywhere in the title, since
    # they don't reliably appear as a clean prefix like "Review:" does
    # -- e.g. "J. Michael Bishop: A remembrance" or "In Science Journals".
    if any(phrase in title for phrase in EXCLUDED_ANYWHERE):
        return False

    # Backup: some feeds put the type in the title itself, e.g.
    # "Correction: ..." or "Editorial: ...".
    if any(title.startswith(excluded + ":") or title.startswith(excluded + " ")
           for excluded in EXCLUDED_TYPES):
        return False

    return True


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def load_matches_log():
    if os.path.exists(MATCHES_LOG_FILE):
        with open(MATCHES_LOG_FILE, "r") as f:
            return json.load(f)
    return []


def save_matches_log(log):
    # Keep newest first, capped to MAX_LOG_ENTRIES.
    with open(MATCHES_LOG_FILE, "w") as f:
        json.dump(log[:MAX_LOG_ENTRIES], f, indent=2)


def matches_keywords(entry):
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    return any(kw.lower() in text for kw in KEYWORDS)


def send_notification(journal, entry):
    article_title = entry.get("title", "New article").strip()
    link = entry.get("link", "")
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=article_title.encode("utf-8"),
        headers={
            "Title": journal.encode("utf-8"),
            "Click": link,
            "Priority": "default",
            "Tags": "dna",
        },
        timeout=15,
    )


def send_heartbeat():
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data="No new articles matched today.".encode("utf-8"),
        headers={
            "Title": "Journal check complete",
            "Priority": "default",  # matches real alerts so it also shows on lock screen
            "Tags": "white_check_mark",
        },
        timeout=15,
    )


def main():
    seen = load_seen()
    new_seen = set(seen)
    matches_log = load_matches_log()
    found_any = False

    for journal, url in FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries:
            article_id = entry.get("id") or entry.get("link")
            if not article_id or article_id in seen:
                continue
            new_seen.add(article_id)
            if matches_keywords(entry) and is_research_article(entry):
                print(f"MATCH [{journal}]: {entry.get('title')}")
                send_notification(journal, entry)
                matches_log.insert(0, {
                    "journal": journal,
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", ""),
                    "date": datetime.datetime.utcnow().isoformat() + "Z",
                })
                found_any = True

    save_seen(new_seen)
    save_matches_log(matches_log)
    if not found_any:
        print("No new matching articles this run.")
        if NOTIFY_ON_NO_MATCHES:
            send_heartbeat()


if __name__ == "__main__":
    main()
