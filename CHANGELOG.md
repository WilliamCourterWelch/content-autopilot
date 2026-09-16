# Changelog

## 0.3.0.0 — 2026-09-16

### Added
- HARD dedupe gate before generate/publish: `data/known-episodes.json`, `data/published.json`, Transistor show episodes, optional globalhighlevel.com slugs
- Committed fingerprint for the 2026-09-16 whitelabel canary (https://share.transistor.fm/s/81da6aeb)
- DISTRIBUTION.md format→channel matrix and auth table
- Drive archive upload when folder id + local token/service-account file exist
- globalhighlevel.com channel is upgrade-into-existing-pillar only (fold brief, no new HTML)
- Beehiiv/Substack stub (no invented list)

### Notes
- `--force` does not bypass dedupe
- Default AI lane remains `--limit 1`

## 0.2.0.0 — 2026-09-16

### Added
- GHL AI multi-format Studio lane: `python3 run.py --ai-lane --formats audio,report,infographic --limit 1`
- Source allowlist for Conversation AI / Voice AI / agent help + changelog URLs
- Pluggable publishers: Transistor (live), YouTube / Drive / social hooks that skip without real credentials
- Tests for format parsing and the AI source filter
- CI workflow (pytest + AI-lane dry-run)

### Fixed
- NotebookLM client now uses notebooklm-py 0.8 (`NotebookLMClient.from_storage`, hardened waiter)
- SEO model comes from `.anthropic_model`
- Transistor authorize field is `audio_url`; create draft then `PATCH /publish`

### Notes
- HARD: no thin new HTML pages on globalhighlevel.com
- Default AI lane is one topic. No volume blast.
