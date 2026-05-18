# Agent Handoff

Updated: 2026-05-18
Agent: codex
Branch: main
Last commit: 8fa3bb7 docs: update agent onboarding for current repo state

## Current Goal

Create a low-token, repo-native handoff flow for switching between Claude and Codex.

## What Changed

- `AGENTS.md` was updated in commit `8fa3bb7` to reflect the real repo state.
- Backend and frontend were verified before that update.
- This handoff system is being added so agents do not need full chat history to continue.

## Files Touched

- `AGENTS.md`
- `.agents/active.md`
- `.agents/handoff.md`
- `.agents/decisions.md`

## Verified

- `pytest tests/ -v`: 56 passed, 1 Pydantic deprecation warning.
- `cd frontend && npm run build`: passed.

## Known Issues

- Plan files still contain unchecked boxes even though much of the work exists.
- Pydantic v2 warns about class-based config style.

## Next Best Step

Review the `.agents/` workflow and commit it if accepted.
