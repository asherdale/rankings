# Rubric

Every site gets the same eight scores from 0 to 100. The composite is their
weighted average, using the weights in [rubric.json](rubric.json), and gets a
letter grade.

| Category | How it's measured |
| --- | --- |
| Speed | [Lighthouse](https://developer.chrome.com/docs/lighthouse) performance score on desktop. |
| Mobile | Lighthouse performance score on a simulated phone. |
| Accessibility | Lighthouse accessibility score on a phone. |
| SEO | Lighthouse SEO score on a phone. |
| Agent readiness | [Ora](https://ora.ai)'s agent-readiness score: how well AI agents can find, read, use, and pay the site. |
| Clarity | An AI reviewer looks at the homepage and scores how quickly a stranger understands what the company does and what to do next. |
| Design | The reviewer scores the desktop and phone screenshots. |
| Copy | The reviewer scores the headline and page text. |

Every review comes from the same model with the same instructions, scored against these anchors:

| Score | Clarity | Design | Copy |
| --- | --- | --- | --- |
| 90+ | A stranger knows what it is and what to do next within five seconds. | Polished and consistent, easy to scan on desktop and phone. | Specific and concrete, with a real voice. |
| 50 | They figure it out after some reading. | Dated or cluttered, but usable. | Generic marketing language. |
| Under 30 | Still unclear after scrolling. | Broken or hard to use. | Confusing or empty. |

| Grade | Composite |
| --- | --- |
| A+ | 95 and up |
| A | 85 to 94 |
| B | 70 to 84 |
| C | 55 to 69 |
| D | 40 to 54 |
| F | Under 40 |

The reviewer also writes a one-sentence roast and the one fix that would help
most.

Each site is measured by Lighthouse on its own machine and visited by an
automated browser that identifies itself as `RateMyHomepage`. If a site blocks
the browser, the review uses Lighthouse's screenshots instead, and the site's
page says so. If it blocks Lighthouse, Google's
[PageSpeed Insights](https://pagespeed.web.dev), which runs the same
Lighthouse from Google's servers, measures it instead. Sites that neither can
load aren't listed.

These scores come from automated tools and an AI model. They're opinions, not
facts, and a rerun can move a score by a few points.

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
  "composite": 71,
  "roast": "One funny, sharp sentence about the site.",
  "fix": "The one fix that would help most.",
  "scores": {
    "speed": 94,
    "mobile": 60,
    "accessibility": 96,
    "seo": 92,
    "agent_readiness": 23,
    "clarity": 82,
    "design": 85,
    "copy": 70
  },
  "notes": {
    "agent_readiness": "Ora's one-sentence summary."
  },
  "model": "openai/gpt-6-luna",
  "blocks_automated_browsers": false,
  "minutes": 2
}
```
