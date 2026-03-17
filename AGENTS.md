## AGENTS.md

## Git/PR

*   Base branch: `master`
*   Branch naming convention:
    *   `feature/<branch-name>` for new features
    *   `fix/<branch-name>` for bug fixes
    *   `chore/<branch-name>` for maintenance/refactor/tooling
*   PR title format: `Summary`
*   PR description must include: Summary, Changes, Testing, Notes
*   Always run `git status` before commit
*   Never commit `.env`
*   If a PR closes a GitHub issue, the PR description must include `Fixes #<issue-number>` so PR and issue are linked automatically

## Security

*   Never log or commit secrets, `.env` and `./code-ref`
*   Use GitHub CLI (`gh`) for GitHub operations (push, PR, issue handling) instead of token-based flows

## General

*   Always answer in Danish unless you are told different in a session
*   Documentation should ALWAYS be in english
*   Keep documentation up-to-date with current code
*   ./code-ref are read-only for AI agents
*   Reference code samples are found in ./code-ref, do not copy code blind - only use as reference
*   ./code-ref/data-samples contains JSON dumps of actual data from real mowers
*   Always push changes to repository, when making changes in a branch
*   Before committing, the agent MUST run the agreed `ruff` commands for this repository, including `ruff format` and `ruff check`, and fix any reported issues

## Release Notes

*   Release notes should ALWAYS be in english
*   Keep the existing release note structure unless explicitly asked to change it
*   The `## Changes` section should be short, easy to read, and written as plain prose without bullets
*   Prefer 2-3 short paragraphs under `## Changes` instead of one dense block of text
*   Base the `## Changes` text only on the PRs already included in the release draft unless told otherwise
