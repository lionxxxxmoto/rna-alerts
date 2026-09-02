"""
Journal Keyword Alert
----------------------
Checks RSS feeds from Nature, Science, and Cell for new articles
matching your keyword(s), and sends a push notification via ntfy.sh
for each new match. Designed to run on a schedule (e.g. GitHub Actions).

Setup:
1. Edit the KEYWORDS and FEEDS lists below if you want.
2. Set your ntfy.sh topic name in the NTFY_TOPIC variable (or as an
   environment variable of the same name -- see README.md).
3. Run: python check_journals.py
"""

import os
import json
import feedparser
import requests

# --- CONFIG -----------------------------------------------------------

# Keywords to watch for (case-insensitive). An article matches if ANY
# of these appear in its title or summary.
KEYWORDS = ["RNA"]

# RSS feeds to check. Add/remove journals here.
FEEDS = {
    "Nature": "https://www.nature.com/nature.rss",
    "Science": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
    "Cell": "https://www.cell.com/cell/current.rss",
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


def send_notification(journal, entry):
    title = f"{journal}: {entry.get('title', 'New article')}"
    link = entry.get("link", "")
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=entry.get("summary", "")[:300].encode("utf-8"),
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
                send_notification(journal, entry)
                found_any = True

    save_seen(new_seen)
    if not found_any:
        print("No new matching articles this run.")
        if NOTIFY_ON_NO_MATCHES:
            send_heartbeat()


if __name__ == "__main__":
    main()
