# RNA Journal Alert

Checks all the major Nature, Science, and Cell family journals (Nature
Genetics, Science Immunology, Molecular Cell, and 25+ others) once a
day at 8am for new articles mentioning your keyword ("RNA" by
default) and sends a simple push notification straight to your phone
-- but only when there's an actual match. No matches, no
notification; you won't hear from it on a quiet day. Notifications
are deliberately minimal: just the article title up front (no journal
name clutter) and a one-sentence summary of the topic. Runs for free
using GitHub Actions -- no server, no computer that needs to stay on.

## Setup (about 15 minutes)

### 1. Install the notification app
- Install **ntfy** from the App Store (iOS) or Google Play (Android).
- Open it, tap "+", and subscribe to a topic name you make up --
  something unique and hard to guess, e.g. `rna-alerts-jt8x2q`.
  (Anyone who knows your topic name can see your notifications, so
  don't use something obvious like `rna-alerts`.)

### 2. Create a GitHub account (if you don't have one)
Free, at github.com.

### 3. Create a new repository
- Click "New repository", name it e.g. `rna-alert`, set it to
  **Public** (needed so the companion web app below can read your
  match history), and create it.
- Upload all the files from this project -- `check_journals.py`,
  `README.md`, `matches_log.json`, `index.html`, `manifest.json`, and
  the `.github/` folder -- by dragging them into the GitHub web
  uploader, or using git if you're comfortable with it.

### 4. Add your ntfy topic as a secret
- In your repo, go to **Settings > Secrets and variables > Actions**.
- Click **New repository secret**.
- Name: `NTFY_TOPIC`
- Value: the topic name you picked in step 1 (e.g. `rna-alerts-jt8x2q`)
- Save.

### 5. Turn on Actions
- Go to the **Actions** tab in your repo and click "I understand my
  workflows, go ahead and enable them" if prompted.
- Click into "Journal Keyword Alert" and click **Run workflow** to
  test it manually.
- Check your phone -- if there's a matching article in the feeds right
  now, you'll get a notification within a minute or two.

That's it. From now on it runs automatically once a day at 8am Eastern.

### 6. Turn on GitHub Pages (for the RNA Watch web app)
- In your repo, go to **Settings > Pages**.
- Under "Build and deployment", set **Source** to "Deploy from a
  branch", set **Branch** to `main` and folder to `/ (root)`, then
  save.
- After a minute or two, your app will be live at
  `https://<your-github-username>.github.io/rna-alert/`.
- Open that link on your iPhone in Safari, tap the **Share** icon,
  then **Add to Home Screen**. You'll get a "RNA Watch" app icon that
  opens full-screen, no browser bar.
- Every day after the script runs, open the app and pull to refresh
  (or just relaunch it) to see the latest matches, filterable by
  journal.

## Customizing

- **Change keywords**: edit the `KEYWORDS` list in `check_journals.py`
  (e.g. `["RNA", "CRISPR", "mRNA vaccine"]`).
- **Add more journals**: add an entry to the `FEEDS` dict with the
  journal's RSS feed URL. Most publishers list theirs under a "RSS" or
  "Alerts" link on their site. Already includes 25+ journals across
  the Nature, Science, and Cell families.
- **Change frequency**: edit the `cron` line in
  `.github/workflows/check.yml` (currently once daily, 8am Eastern).

## How it works

1. GitHub Actions wakes up once a day at 8am Eastern and runs
   `check_journals.py` in a temporary cloud machine.
2. The script downloads each journal's RSS feed and checks new
   entries' titles/summaries for your keyword.
3. **Only if there's a match**, it sends a notification to your
   ntfy.sh topic and logs the article to `matches_log.json`.
   No matches that day means no notification at all.
4. It saves `seen_articles.json` (so it never alerts you twice for the
   same article) and `matches_log.json` (the last 500 matches, newest
   first) back to your repo.
5. The RNA Watch web app (`index.html`) reads `matches_log.json`
   straight from your public repo and displays it as a filterable
   list -- no separate backend needed.

Note: GitHub Actions schedules can occasionally run a few minutes
late during high-traffic periods -- this is normal and not a bug.
