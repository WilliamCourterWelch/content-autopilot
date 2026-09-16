# Changelog

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
