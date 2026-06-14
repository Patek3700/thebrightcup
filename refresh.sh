#!/bin/bash
# refresh.sh — rebuild The Bright Cup with fresh good news and publish to GitHub
# Pages. Run hourly by cron on the Mini. build.py uses only the Python stdlib,
# so system python3 is fine.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:$HOME/.local/node/bin:$HOME/.local/bin:/usr/bin:/bin"
/usr/bin/python3 build.py >> /tmp/brightcup.log 2>&1
git add -A
if ! git diff --cached --quiet; then
  git -c user.name="Patek3700" -c user.email="jlsilverman1@gmail.com" \
      commit -q -m "hourly refresh: fresh good news"
  git push -q origin main
  echo "[$(date)] pushed update" >> /tmp/brightcup.log
else
  echo "[$(date)] no changes" >> /tmp/brightcup.log
fi
