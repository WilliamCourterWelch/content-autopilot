# Distribution map

Studio artifacts do not sit in `data/` as the end state. Each format maps to owned channels. Missing auth skips with a log. **No invented credentials.**

Default AI lane: `--limit 1`. Dedupe gate runs before generate/publish.

## Format → channel

| Format | Transistor (Spotify/Apple) | YouTube | Drive archive | globalhighlevel.com | Social (LI/X/FB) | Beehiiv/Substack |
|--------|----------------------------|---------|---------------|---------------------|------------------|------------------|
| audio | **live** | — | live (when folder + token) | — | stub | — |
| video | — | stub (channel OAuth later) | live (when folder + token) | — | stub | — |
| slide-deck | — | — | live | upgrade existing pillar only | — | — |
| report | — | — | live | upgrade existing pillar only | — | stub |
| infographic | — | — | live | upgrade existing pillar only | stub | — |
| mind-map | — | — | live | — | — | — |
| quiz | — | — | live | — | — | — |
| flashcards | — | — | live | — | — | — |

Source of truth in code: `scripts/distribution.py`.

## Auth per channel

| Channel | Status | Env (never commit values) | Notes |
|---------|--------|---------------------------|-------|
| Transistor | live | `TRANSISTOR_API_KEY`, `TRANSISTOR_SHOW_ID` | Draft then `PATCH /publish`. Feeds Spotify, Apple, Amazon. Dedupe lists show episodes first. |
| Google Drive | live | `GOOGLE_DRIVE_FOLDER_ID` (config) + `GOOGLE_DRIVE_TOKEN` or `GOOGLE_DRIVE_CREDENTIALS` | Artifact archive. Folder id is not a secret; token files stay local. |
| YouTube | stub | `YOUTUBE_CLIENT_SECRETS`, `YOUTUBE_TOKEN` | Need channel auth later. No client ids in repo. |
| globalhighlevel.com | **upgrade-only** | `GHL_PILLAR_PAGES` or `data/pillar-pages.json`; optional `GHL_SITE_UPGRADE_WEBHOOK` | Fold into an existing pillar/money page. **NEVER spray a thin new HTML post.** Prior Google demotion came from ~850 thin NotebookLM pages. |
| Social | stub | `SOCIAL_BUFFER_ACCESS_TOKEN` or `SOCIAL_API_TOKEN` | LinkedIn / X / Facebook. |
| Beehiiv / Substack | stub | `BEEHIIV_API_KEY` or `SUBSTACK_PUBLICATION_URL` | Only if GHL already has a list. Do not invent a publication. |

## Dedupe gate (HARD)

Before generate or publish, skip if the topic is already done:

1. `data/known-episodes.json` — committed fingerprints (includes the 2026-09-16 [whitelabel canary](https://share.transistor.fm/s/81da6aeb))
2. `data/published.json` — `source_url` + normalized title
3. Transistor show episodes — title / source fingerprint (when API keys exist)
4. Optional: existing `globalhighlevel.com` slugs (`GHL_SITE_DEDUPE_URL` / `SITE_URL`) and pillar pages

`--force` does **not** bypass this gate. The whitelabel help article must never ship a second episode.

## Anti-thin-site rule

`globalhighlevel.com` is not a blog dump. If there is no matching pillar in `data/pillar-pages.json`, the site channel skips. A match writes a fold brief under `data/site-upgrades/` (local, gitignored) instead of a new public URL.
