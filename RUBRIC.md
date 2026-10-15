# How sites are scored

Every site gets its own machine and AI agent. The agent opens the homepage in
a real browser, takes screenshots, and hands them to four AI judges: Claude,
GPT, Gemini, and Muse. Each result file records the exact model behind each judge.

Each judge sees the same screenshots of the desktop homepage, the phone view,
and the full page, plus the page's text. It scores the
homepage from 1 to 10 on how quickly a stranger understands what it is and
what to do next, how good it looks on desktop and phone, and how good the
writing is. Then it writes a one-line roast. The judges work separately and
never see each other's scores.

Each site's page also shows five measurements. They don't change the score.
Lighthouse and Ora score from 0 to 100; the site shows them out of 10 like
everything else:

| Measurement | How it's measured |
| --- | --- |
| Mobile speed | [Lighthouse](https://developer.chrome.com/docs/lighthouse) performance score on a simulated phone. |
| Desktop speed | Lighthouse performance score on desktop. |
| Accessibility | Lighthouse accessibility score on a phone. |
| SEO | Lighthouse SEO score on a phone. |
| Agent readiness | [Ora](https://ora.ai)'s score for how well AI agents can find, read, and use the site. |

A measurement that Lighthouse or Ora can't take shows as n/a.

The site's score is the judges' average, rounded to one decimal, and gets a
letter grade. Sites with the same score are ordered by their average
measurement.

| Grade | Score |
| --- | --- |
| A+ | 9.5 and up |
| A | 8.5 to 9.4 |
| B | 7 to 8.4 |
| C | 5.5 to 6.9 |
| D | 4 to 5.4 |
| F | Under 4 |

Each site is visited by an automated browser that identifies itself as
`RateMyHomepage`. If a site blocks the browser, the judges see Lighthouse's
screenshots instead, and the site's page says so. If it blocks Lighthouse,
Google's [PageSpeed Insights](https://pagespeed.web.dev), which runs the same
Lighthouse from Google's servers, measures it instead. Sites that neither can
load aren't listed. If only Lighthouse fails, the site is still judged and its
Lighthouse measurements show as n/a.

These scores are opinions from AI models, not facts, and a rerun can move a
score.

## Result files

Each ranked site has a result at `results/<domain>.json`, a homepage
screenshot at `shots/<domain>.jpg`, and a share card at `cards/<domain>.jpg`.
While a site is being scored, its result is just `domain` and
`"status": "scoring"`.

```json
{
  "domain": "example.com",
  "status": "done",
  "audited_at": "2026-10-14T18:20:00Z",
  "score": 6.5,
  "judges": {
    "claude": { "model": "anthropic/claude-haiku-5.5", "score": 7, "roast": "One funny, sharp sentence." },
    "gpt": { "model": "openai/gpt-5-nano", "score": 5, "roast": "One funny, sharp sentence." },
    "gemini": { "model": "google/gemini-3.5-flash-lite", "score": 7, "roast": "One funny, sharp sentence." },
    "muse": { "model": "meta/muse-glimmer-30b", "score": 7, "roast": "One funny, sharp sentence." }
  },
  "mobile_speed": 41,
  "desktop_speed": 88,
  "accessibility": 96,
  "seo": 92,
  "agent_readiness": 23,
  "agent_readiness_summary": "Ora's one-sentence summary.",
  "blocks_automated_browsers": false,
  "minutes": 2
}
```
