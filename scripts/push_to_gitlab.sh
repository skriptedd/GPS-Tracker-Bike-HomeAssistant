#!/usr/bin/env bash
# Pusht dieses Repo nach GitLab.
#   ./scripts/push_to_gitlab.sh glpat-xxxxxxxx https://gitlab.example.org/user/repo.git
set -euo pipefail

TOKEN="${1:?Usage: $0 <gitlab-token> <remote-url> [branch]}"
REMOTE="${2:?Usage: $0 <gitlab-token> <remote-url> [branch]}"
BRANCH="${3:-main}"

cd "$(dirname "$0")/.."
echo "Repo: $PWD"

if [ ! -d .git ]; then
  git init
  git checkout -b "$BRANCH"
fi

git add -A
if ! git diff --cached --quiet; then
  git -c user.name="Bike Tracker" -c user.email="bike-tracker@local" \
      commit -m "Bike Tracker: Home Assistant Integration"
else
  echo "Keine Aenderungen zu committen."
fi

git remote get-url origin >/dev/null 2>&1 \
  && git remote set-url origin "$REMOTE" \
  || git remote add origin "$REMOTE"

# Token nur fuer diesen Push, nicht dauerhaft speichern.
AUTH_URL="${REMOTE/https:\/\//https://oauth2:${TOKEN}@}"
git push -u "$AUTH_URL" "${BRANCH}:${BRANCH}"

echo "Fertig: $REMOTE"
