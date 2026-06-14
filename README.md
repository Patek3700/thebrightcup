# The Bright Cup ☕

Good news, daily. A calm landing page + the day's good news sorted into topics,
a rotating Daily Meditation, Little Gems, and a "Leave a Note" form.

- `build.py` — fetches curated good-news RSS feeds and generates the static
  site (`index.html` + one page per topic). Zero-JS pages (a small countdown
  script is the only JS). Run: `python build.py`
- `feeds.json` / `quotes.json` / `gems.json` — content sources.
- Deploys automatically via GitHub Pages + Actions, rebuilding hourly.

A JDog Production.
