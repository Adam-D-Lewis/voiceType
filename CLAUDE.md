# VoiceType Project Instructions

## Git Workflow

- **Always create PRs** for merging feature branches to main (don't merge directly)
- Use `.worktrees/` for isolated development

## Git Worktrees

**IMPORTANT:** After creating a git worktree, you MUST initialize submodules:

```bash
git worktree add .worktrees/<name> -b <branch-name>
cd .worktrees/<name>
git submodule update --init --recursive
```

The project has a vendored pynput submodule that won't work without this step.
