#!/usr/bin/env bash
# Person A runs this ONCE, after creating an EMPTY repo on GitHub/GitLab (no README, no .gitignore).
# Usage: bash scripts/bootstrap_git.sh git@github.com:<org>/cascade-sentinel.git
set -euo pipefail
REMOTE="${1:?usage: bootstrap_git.sh <remote-url>}"
git init -b main
git add .
git commit -m "chore: import CASCADE SENTINEL v2 reference scaffold"
git remote add origin "$REMOTE"
git push -u origin main
git switch -c develop && git push -u origin develop
git tag -a v0.1-scaffold -m "scaffold imported" && git push origin v0.1-scaffold
echo "Done. Person B: git clone $REMOTE && cd cascade-sentinel && git switch develop"
