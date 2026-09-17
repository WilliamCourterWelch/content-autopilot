# Distribution map

Studio artifacts do not sit in `data/` as the end state unless the format has no audience. Each format maps to owned channels. Missing auth skips with a log. **No invented credentials.**

**Google Drive is not a publish destination.** Drive is not an audience. Optional local scratch under `data/` is fine. Do not treat a Drive folder as distribution.

Default AI lane: `--limit 1`. Topic picker + dedupe gate run before generate/publish.

## Topic picker

`scripts/topic_picker.py` chooses what to generate. Pipeline:

1. **Scrape** recent `help.gohighlevel.com` search + changelog indexes (`ideas.gohighlevel.com/changelog`, `changelog.gohighlevel.com`, `updates.gohighlevel.com`) for GHL AI keywords (Conversation AI, Voice AI, agents, AI employee, AI receptionist, …)
2. **Hard dedupe** against Transistor show episodes, `data/published.json`, `data/known-episodes.json`, and optional globalhighlevel.com slugs / pillars
3. **Rank** remaining topics by money-adjacent score (Conversation AI / Voice AI / AI employee / booking / inbound / outbound beat generic chatbot how-tos; changelog + last-90-day dates get a bump)
4. **Return** the top N. Default `--limit 1`. Above 3 requires `--force`

Pinned `--url` still bypasses ranking but not the AI allowlist or the generate/publish dedupe gate.

## Format → channel

Publish targets only: Transistor/Spotify (audio), YouTube (video), globalhighlevel.com pillar/money-page **folds** (no thin new posts), social stubs.

| Format | Transistor (Spotify/Apple) | YouTube | globalhighlevel.com | Social (LI/X/FB) | Local scratch |
|--------|----------------------------|---------|---------------------|------------------|---------------|
| audio | **live** | — | — | stub | `data/audio/` |
| video | — | **live** (`videos.insert`, default unlisted) | — | stub | `data/video/` |
| slide-deck | — | — | upgrade existing pillar only | — | `data/slides/` |
| report | — | — | upgrade existing pillar only | — | `data/reports/` |
| infographic | — | — | upgrade existing pillar only | stub | `data/infographics/` |
| mind-map | — | — | — | — | **only** (`data/mindmaps/`) |
| quiz | — | — | — | — | **only** (`data/quizzes/`) |
| flashcards | — | — | — | — | **only** (`data/flashcards/`) |

Source of truth in code: `scripts/distribution.py`. There is no Drive column.

## Auth per channel

| Channel | Status | Env (never commit values) | Notes |
|---------|--------|---------------------------|-------|
| Transistor | live | `TRANSISTOR_API_KEY`, `TRANSISTOR_SHOW_ID` | Draft then `PATCH /publish`. Feeds Spotify, Apple, Amazon. Dedupe lists show episodes first. |
| YouTube | **live** | `YOUTUBE_CLIENT_SECRETS`, `YOUTUBE_TOKEN` (file **paths** only); optional `YOUTUBE_PRIVACY=unlisted\|public` (default **unlisted**) | Channel [@williamcourterwelch](https://www.youtube.com/@williamcourterwelch). `googleapiclient` `videos.insert` + token refresh via `google.oauth2.credentials` + `Request`. On the Grok box: `YOUTUBE_CLIENT_SECRETS=/home/box/.secrets/youtube-oauth-client.json` and `YOUTUBE_TOKEN=/home/box/.secrets/youtube-oauth-token.json`. Never commit those files or paste secrets into git. |

## Description CTA (YouTube + Transistor)

Every YouTube and Transistor description always includes:

1. The plain-English trial line: `Want a GoHighLevel 30-day free trial? Link in the description.`
2. The bootcamp URL from `AFFILIATE_LINK` or `GHL_AFFILIATE_LINK` (if set — never invent a URL)

Helper: `scripts.seo.with_trial_cta`. Idempotent if the line/link is already present.
| globalhighlevel.com | **upgrade-only** | `GHL_PILLAR_PAGES` or `data/pillar-pages.json`; optional `GHL_SITE_UPGRADE_WEBHOOK` | Fold into an existing pillar/money page. **NEVER spray a thin new HTML post.** Prior Google demotion came from ~850 thin NotebookLM pages. |
| Social | stub | `SOCIAL_BUFFER_ACCESS_TOKEN` or `SOCIAL_API_TOKEN` | LinkedIn / X / Facebook. |

`GOOGLE_DRIVE_*` is not used. A local folder is scratch, not distribution.

## Dedupe gate (HARD)

Before generate or publish, skip if the topic is already done:

1. `data/known-episodes.json` — committed fingerprints (includes the 2026-09-16 [whitelabel canary](https://share.transistor.fm/s/81da6aeb))
2. `data/published.json` — `source_url` + normalized title
3. Transistor show episodes — title / source fingerprint (when API keys exist)
4. Optional: existing `globalhighlevel.com` slugs (`GHL_SITE_DEDUPE_URL` / `SITE_URL`) and pillar pages

`--force` does **not** bypass this gate. The whitelabel help article must never ship a second episode. The topic picker applies the same gate before ranking.

## Anti-thin-site rule

`globalhighlevel.com` is not a blog dump. If there is no matching pillar in `data/pillar-pages.json`, the site channel skips. A match writes a fold brief under `data/site-upgrades/` (local, gitignored) instead of a new public URL.
