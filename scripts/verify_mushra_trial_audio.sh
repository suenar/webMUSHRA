#!/usr/bin/env bash
# Sanity-check MUSHRA trial folders: all MP3s in a trial share duration, sample_rate, channels; duration < 12s.
# Usage: ./scripts/verify_mushra_trial_audio.sh [root_dir]

set -euo pipefail
ROOT="${1:-configs/resources/audio/violin-valle}"

if ! command -v ffprobe >/dev/null 2>&1; then
  echo "ERROR: ffprobe not on PATH" >&2
  exit 1
fi

fail=0
while IFS= read -r dir; do
  [[ -d "$dir" ]] || continue
  sig=""
  max_d="0"
  for f in "$dir"/*.mp3; do
    [[ -f "$f" ]] || continue
    d="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" | tr -d ' \r\n')"
    sr="$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$f" | tr -d ' \r\n')"
    ch="$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$f" | tr -d ' \r\n')"
    sig+="${d}|${sr}|${ch}"$'\n'
    max_d="$(awk -v a="$max_d" -v b="$d" 'BEGIN{ print (a+0 > b+0) ? a : b }')"
  done
  nuniq="$(printf '%s' "$sig" | sort -u | grep -c . || true)"
  if [[ "$nuniq" -ne 1 ]]; then
    echo "FAIL inconsistent (dur|sr|ch) in: $dir"
    printf '%s' "$sig" | sort | uniq -c
    fail=1
    continue
  fi
  if ! awk -v m="$max_d" 'BEGIN{ exit (m + 0 < 12.0 ? 0 : 1) }'; then
    echo "FAIL max duration >= 12s in $dir (max=$max_d)"
    fail=1
  fi
done < <(find "$ROOT" -type d -name 'trial_*' | sort)

if [[ "$fail" -eq 0 ]]; then
  echo "OK: all trial_* folders have uniform MP3 params and duration < 12s"
else
  exit 1
fi
