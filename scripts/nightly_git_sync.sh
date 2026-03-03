#!/usr/bin/env bash
set -euo pipefail

cd /Users/josefhofman/.openclaw/workspace

is_sensitive_path() {
  case "$1" in
    .secrets/*|.private/*|.openclaw/*|monitoring/*|workspace/pipedrive/*|pipedrive/*|memory/*|inbox/*|calendar/*|knowledge/*|intel/*|reviews/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

mapfile -t staged_paths < <(git diff --cached --name-only)
for path in "${staged_paths[@]}"; do
  if is_sensitive_path "$path"; then
    echo "$(date '+%F %T') refusing to sync staged sensitive path: $path"
    exit 1
  fi
done

mapfile -t changed_paths < <(git ls-files --modified --others --deleted --exclude-standard)
if [[ ${#changed_paths[@]} -eq 0 ]]; then
  echo "$(date '+%F %T') no changes"
  exit 0
fi

safe_paths=()
sensitive_paths=()
for path in "${changed_paths[@]}"; do
  if is_sensitive_path "$path"; then
    sensitive_paths+=("$path")
  else
    safe_paths+=("$path")
  fi
done

if [[ ${#sensitive_paths[@]} -gt 0 ]]; then
  printf '%s skipped sensitive paths:\n' "$(date '+%F %T')"
  printf ' - %s\n' "${sensitive_paths[@]}"
fi

if [[ ${#safe_paths[@]} -eq 0 ]]; then
  echo "$(date '+%F %T') no syncable changes"
  exit 0
fi

# Auto-commit and push only non-sensitive files
TS="$(date '+%Y-%m-%d %H:%M')"
git add -A -- "${safe_paths[@]}"

if git diff --cached --quiet; then
  echo "$(date '+%F %T') no staged syncable changes"
  exit 0
fi

git commit -m "chore: nightly sync ${TS}" || true

# Rebase to avoid non-fast-forward failures
(git fetch origin main && git rebase origin/main) || (git rebase --abort || true)

git push origin main

echo "$(date '+%F %T') pushed"
