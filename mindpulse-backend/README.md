# MindPulse Backend

Adds persistence, a dashboard, and basic analytics on top of the MindPulse
front-end — all 9 test/game pages are now wired up and saving results.

## What's in here

```
mindpulse-backend/
  app.py                Flask API + serves the front-end
  requirements.txt
  public/
    tracker.js            Shared helper: anonymous user id + saveResult()
    index.html             Landing page (unchanged)
    selection.html          Test hub + "Your Dashboard" card
    dashboard.html           Trend charts + insights, pulls from the API
    mood.html                Mood scenario quiz — saves score/45
    iq.html                  IQ quiz — saves score/15
    personality.html          Personality quiz — saves score/45
    color.html                 Color psychology quiz — saves dominant-color count/10
    decision.html               Decision speed game — saves accuracy % (0-100)
    focus.html                   Focus catch game — saves catch count (open-ended)
    memory.html                    Memory flip — saves highest level reached (1-3)
    sequence.html                   Sequence finder — saves completion time in seconds
                                     (lower is better, noted in the label)
    games.html                       Games hub + dashboard link
```

## Running it

```bash
cd mindpulse-backend
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 — that's `selection.html`. Take a few tests,
then click "Your Dashboard" to see them save and chart.

Note: `index.html` references `image.png` and `log.jpeg` for the landing
page background/logo — add your own copies of those into `public/` since
they weren't part of this backend integration.

## How it works

- **No login system was added.** Each browser generates a random id on
  first visit (`tracker.js`, stored in `localStorage`) and every result is
  tagged with it. Simple, and matches the "no accounts" feel of the
  original app.
- **`saveResult(...)`** in `tracker.js` POSTs to `/api/results`. It fails
  silently (console warning only) if the backend is down, so a quiz never
  breaks because of it.
- **`/api/summary/<user_id>`** returns per-test attempt count, average,
  best score, latest score, and trend (first attempt vs. latest) — this is
  what powers the dashboard cards and charts.
- **`/api/insights/<user_id>`** does two things:
  - Correlates your own scores across test types (e.g. do your mood and
    focus scores move together?), once you have at least 3 attempts of
    each.
  - Trains a logistic regression **across all users** predicting
    below-median mood from focus + memory scores — but only once at least
    20 users have all three. Until then it honestly says there isn't
    enough data yet, rather than showing a made-up number.

## Scoring notes (for your own reference / interview prep)

Because the 9 original pages weren't designed with a shared scoring
convention, each maps to `saveResult` slightly differently:

| Test | Score meaning | max_score |
|---|---|---|
| mood | weighted scenario score | 45 |
| iq | correct answers | 15 |
| personality | weighted scenario score | 45 |
| color | count of dominant color chosen | 10 |
| decision | accuracy percentage | 100 |
| focus | number of correct catches | none (open-ended) |
| memory | highest level completed | 3 |
| sequence | seconds to complete (lower = better) | none |

The dashboard charts these as-is. Sequence is the one exception where a
**lower** number is the better result — worth mentioning if you demo this,
since every other test's chart trending up is "improving" but sequence's
trending down is the improving direction.

## Where this could go next

- Deploy (Render/PythonAnywhere) so the link is live and shareable.
- Swap the median-split "low mood" label for something more principled
  once there's more data.
- Add a `/api/export/<user_id>` CSV endpoint if you want to pull data into
  a notebook for a deeper analysis write-up (good for a resume bullet on
  its own).
- Normalize scoring (e.g. convert everything to a 0-100 scale) if you want
  cross-test correlations to be more directly comparable.
