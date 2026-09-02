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
import re
import json
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
    "Nature Reviews Genetics": "https://www.nature.com/nrg.rss",
    "Nature Reviews Molecular Cell Biology": "https://www.nature.com/nrm.rss",

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

# If True, sends a low-priority "checked, nothing new" notification on
# days with no matches -- useful as a heartbeat to confirm it's still
# running. Set to False to go back to only hearing about real matches.
NOTIFY_ON_NO_MATCHES = True

# --- LOGIC --------------------------------------------------------------

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def matches_keywords(entry):
    text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    return any(kw.lower() in text for kw in KEYWORDS)


def clean_summary(entry):
    """Strip HTML and return just the first sentence of the abstract,
    so the notification body is a short one-line topic summary rather
    than a full (often HTML-tagged) abstract dump."""
    raw = entry.get("summary", "")
    text = re.sub(r"<[^>]+>", " ", raw)          # strip HTML tags
    text = re.sub(r"\s+", " ", text).strip()      # collapse whitespace
    if not text:
        return "New article published."
    # Split on sentence-ending punctuation followed by a space/capital.
    match = re.match(r"(.{20,300}?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text[:200]
    return sentence


def send_notification(entry):
    title = entry.get("title", "New article").strip()
    link = entry.get("link", "")
    body = clean_summary(entry)
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
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
            "Priority": "min",  # low priority: silent/no-buzz on most phones
            "Tags": "white_check_mark",
        },
        timeout=15,
    )


def main():
    seen = load_seen()
    new_seen = set(seen)
    found_any = False

    for journal, url in FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries:
            article_id = entry.get("id") or entry.get("link")
            if not article_id or article_id in seen:
                continue
            new_seen.add(article_id)
            if matches_keywords(entry):
                print(f"MATCH [{journal}]: {entry.get('title')}")
                send_notification(entry)
                found_any = True

    save_seen(new_seen)
    if not found_any:
        print("No new matching articles this run.")
        if NOTIFY_ON_NO_MATCHES:
            send_heartbeat()


if __name__ == "__main__":
    main()
