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

# File the web app reads to show a "hottest paper this week" section
# at the top, based on Altmetric attention scores (see pick_featured()
# below). Written fresh on every run; empty object if nothing qualifies.
FEATURED_FILE = "featured.json"

# How many days back counts as "this week" for the featured pick.
FEATURED_WINDOW_DAYS = 7

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
    "podcast",
]

# --- LOGIC --------------------------------------------------------------

def is_research_article(entry):
    """Returns False if the entry's category/section or title marks it
    as a review, editorial, news piece, correction, podcast, etc."""
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

    # Podcasts get a plain substring check -- episode titles are often
    # formatted like "Nature Podcast: 21 August 2026", so the word
    # doesn't sit at the start of the title like "Review:" etc. do.
    if "podcast" in title:
        return False

    # Backup: some feeds put the type in the title itself, e.g.
    # "Correction: ..." or "Editorial: ...".
    if any(title.startswith(excluded + ":") or title.startswith(excluded + " ")
           for excluded in EXCLUDED_TYPES):
        return False

    return True

def extract_doi(link, journal):
    """Best-effort DOI extraction from an article's URL, used to look
    up its Altmetric attention score. Returns None if it can't be
    determined -- that article is simply skipped from the featured
    pick rather than causing an error.

    - Nature-family URLs (nature.com/articles/<code>) map directly to
      10.1038/<code> -- Springer Nature uses one DOI prefix site-wide.
    - Science-family URLs embed the DOI directly after "/doi/".
    - Cell-family (ScienceDirect) URLs use a "PII" identifier that
      does NOT reliably map to a DOI without an extra lookup, so these
      return None and are excluded from the featured comparison.
    """
    if "nature.com" in link:
        m = re.search(r"/articles/([A-Za-z0-9\-\.]+)", link)
        if m:
            return f"10.1038/{m.group(1)}"
    elif "science.org" in link:
        m = re.search(r"/doi/(?:abs/|full/|pdf/)?(10\.\d{4,9}/\S+?)(?:[?#]|$)", link)
        if m:
            return m.group(1)
    # Cell/ScienceDirect and anything else: no reliable extraction.
    return None


def get_altmetric_score(doi):
    """Looks up a DOI's Altmetric attention score via the free public
    API. Returns a float score, or None if there's no data yet or the
    lookup fails for any reason (never raises -- a missing score just
    means that article can't be considered for the featured pick).
    Prints what happened for each lookup so failures are diagnosable."""
    try:
        resp = requests.get(f"https://api.altmetric.com/v1/doi/{doi}", timeout=10)
        if resp.status_code != 200:
            print(f"  Altmetric lookup for {doi}: HTTP {resp.status_code}")
            return None
        data = resp.json()
        score = data.get("score")
        print(f"  Altmetric lookup for {doi}: score={score}")
        return score
    except requests.RequestException as e:
        print(f"  Altmetric lookup for {doi}: request failed ({e})")
        return None


def pick_featured(matches_log):
    """Looks at every logged match from the last FEATURED_WINDOW_DAYS
    with a resolvable DOI, fetches its current Altmetric score, and
    returns the highest-scoring one as a dict -- or None if nothing in
    the window has a score (e.g. all-Cell week, or Altmetric is down).
    Prints a breakdown so a "no pick" result is easy to diagnose."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=FEATURED_WINDOW_DAYS)
    cutoff_str = cutoff.isoformat()

    in_window = 0
    with_doi = 0
    with_score = 0
    best = None

    for entry in matches_log:
        if entry.get("date", "") < cutoff_str:
            continue
        in_window += 1
        doi = entry.get("doi") or extract_doi(entry.get("link", ""), entry.get("journal", ""))
        if not doi:
            continue
        with_doi += 1
        score = get_altmetric_score(doi)
        if score is None:
            continue
        with_score += 1
        if best is None or score > best["score"]:
            best = {
                "journal": entry.get("journal"),
                "title": entry.get("title"),
                "link": entry.get("link"),
                "score": score,
                "as_of": datetime.datetime.utcnow().isoformat() + "Z",
            }

    print(f"Featured pick diagnostics: {in_window} matches in the last "
          f"{FEATURED_WINDOW_DAYS} days, {with_doi} had a resolvable DOI, "
          f"{with_score} had an Altmetric score.")
    return best


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
                link = entry.get("link", "")
                matches_log.insert(0, {
                    "journal": journal,
                    "title": entry.get("title", "").strip(),
                    "link": link,
                    "date": datetime.datetime.utcnow().isoformat() + "Z",
                    "doi": extract_doi(link, journal),
                })
                found_any = True

    save_seen(new_seen)
    save_matches_log(matches_log)

    featured = pick_featured(matches_log)
    with open(FEATURED_FILE, "w") as f:
        json.dump(featured or {}, f, indent=2)
    if featured:
        print(f"Featured: [{featured['journal']}] {featured['title']} (score {featured['score']})")
    else:
        print("No featured pick this run (no scored articles in the window).")

    if not found_any:
        print("No new matching articles this run.")
        if NOTIFY_ON_NO_MATCHES:
            send_heartbeat()


if __name__ == "__main__":
    main()
