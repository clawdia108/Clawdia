#!/usr/bin/env bash
set -euo pipefail

cd /Users/josefhofman/.openclaw/workspace

# Skip if nothing changed
if [[ -z "$(git status --porcelain)" ]]; then
  echo "$(date '+%F %T') no changes"
  exit 0
fi

# Auto-commit and push
TS="$(date '+%Y-%m-%d %H:%M')"
git add -A
git commit -m "chore: nightly sync ${TS}" || true

# Rebase to avoid non-fast-forward failures
(git fetch origin main && git rebase origin/main) || (git rebase --abort || true)

git push origin main

echo "$(date '+%F %T') pushed"
