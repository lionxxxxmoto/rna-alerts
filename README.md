# RNA Journal Alert

Checks Nature, Science, and Cell every hour for new articles mentioning
your keyword ("RNA" by default) and sends a push notification straight
to your phone. Runs for free using GitHub Actions -- no server, no
computer that needs to stay on.

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
  **Private**, and create it.
- Upload the three files/folders from this project
  (`check_journals.py`, `README.md`, and the `.github/` folder)
  by dragging them into the GitHub web uploader, or using git if
  you're comfortable with it.

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

That's it. From now on it runs automatically every hour.

## Customizing

- **Change keywords**: edit the `KEYWORDS` list in `check_journals.py`
  (e.g. `["RNA", "CRISPR", "mRNA vaccine"]`).
- **Add more journals**: add an entry to the `FEEDS` dict with the
  journal's RSS feed URL. Most publishers list theirs under a "RSS" or
  "Alerts" link on their site.
- **Change frequency**: edit the `cron` line in
  `.github/workflows/check.yml` (it's currently every hour).

## How it works

1. GitHub Actions wakes up on the schedule you set and runs
   `check_journals.py` in a temporary cloud machine.
2. The script downloads each journal's RSS feed and checks new
   entries' titles/summaries for your keyword.
3. For each match, it sends a notification to your ntfy.sh topic.
4. It saves a small `seen_articles.json` file back to your repo so it
   never alerts you twice for the same article.
