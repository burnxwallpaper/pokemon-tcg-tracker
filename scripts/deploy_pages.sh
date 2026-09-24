#!/usr/bin/env bash
# Deploy data/dashboard snapshot to burnxwallpaper/pokemon-tcg-tracker (GitHub Pages)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEED_TOKEN=1
if [[ -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]]; then
  echo "GH_TOKEN missing" >&2
  exit 2
fi
export GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"
WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
mkdir -p "$WORKDIR"
cp -a "$ROOT/dashboard/index.html" "$WORKDIR/index.html"
mkdir -p "$WORKDIR/data"
cp -a "$ROOT/data/." "$WORKDIR/data/"
# Pages paths
python3 - <<PY
from pathlib import Path
p = Path("$WORKDIR/index.html")
t = p.read_text()
t = t.replace('"../data/', '"./data/').replace("'../data/", "'./data/")
p.write_text(t)
PY
cd "$WORKDIR"
git init -b main
git config user.email "pokemon-tcg-tracker@local"
git config user.name "pokemon-tcg-tracker"
git add -A
git commit -m "Daily dashboard update $(date +%Y-%m-%d)" || true
git remote add origin "https://x-access-token:${GH_TOKEN}@github.com/burnxwallpaper/pokemon-tcg-tracker.git"
git push -u origin main --force
git remote set-url origin https://github.com/burnxwallpaper/pokemon-tcg-tracker.git
echo "Deployed https://burnxwallpaper.github.io/pokemon-tcg-tracker/"
