# AGENTS.md

## Git/PR

- Base branch: `main`
- Feature branch prefix: `codex/`
- PR title format: `Summary`
- PR description must include: Summary, Changes, Testing, Notes
- Always run `git status` before commit
- Never commit `.env`
- If a branch fixes an known github issue, include the text `Fixes #` and the issue number, so the PR and issue gets linked

## Security

- Never log or commit secrets, `.env` and `./code-ref`
- Use `AI_GITHUB_TOKEN` in `.env`, if present, for Github push,PR, issue creation and handling

## General

- Always answer in Danish unless you are told different in a session
- Documentation should ALWAYS be in english
- Keep documentation up-to-date with current code