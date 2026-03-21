#!/usr/bin/env bash
# Normalize MUSHRA trial MP3s for webMUSHRA validation:
# - If probed duration >= 12.0s: trim to TRIM_SECONDS (below 12s) so browser MP3 decode stays under 12s.
# - If probed duration < 12.0s: leave file unchanged (no trim, no re-encode).
#
# Requires: ffmpeg, ffprobe (e.g. conda env "audio").
# Usage: from repo root — ./scripts/normalize_mushra_audio.sh [root_dir]
# Default root_dir: configs/resources/audio/violin-valle

set -euo pipefail

ROOT="${1:-configs/resources/audio/violin-valle}"
TRIM_SECONDS="${TRIM_SECONDS:-11.90}"
THRESHOLD="${THRESHOLD:-12.0}"

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "ERROR: ffmpeg and ffprobe must be on PATH (try: conda activate audio)" >&2
  exit 1
fi

shopt -s nullglob
count_trim=0
count_skip=0
count_err=0

while IFS= read -r -d '' f; do
  duration="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null | tr -d ' \r\n' || true)"
  if [[ -z "$duration" ]]; then
    echo "ERROR: could not probe duration: $f" >&2
    ((count_err++)) || true
    continue
  fi

  # Trim only if duration >= THRESHOLD (awk avoids bash float issues; exit 0 => do trim)
  if awk -v d="$duration" -v t="$THRESHOLD" 'BEGIN{ if (d + 0 >= t + 0) exit 0; exit 1 }'; then
    # Output must end in .mp3 (or use -f mp3) so ffmpeg picks the muxer
    tmp="${f%.mp3}.trim.$$.mp3"
    if ffmpeg -y -hide_banner -loglevel error -i "$f" -t "$TRIM_SECONDS" -ar 32000 -ac 1 -c:a libmp3lame -b:a 128k -f mp3 "$tmp" \
      && mv "$tmp" "$f"; then
      echo "TRIM  ($duration s -> ${TRIM_SECONDS}s): $f"
      ((count_trim++)) || true
    else
      rm -f "$tmp"
      echo "ERROR: ffmpeg failed: $f" >&2
      ((count_err++)) || true
    fi
  else
    echo "SKIP  (${duration}s < ${THRESHOLD}s, unchanged): $f"
    ((count_skip++)) || true
  fi
done < <(find "$ROOT" -type f -name '*.mp3' -print0 | sort -z)

echo ""
echo "Done. trimmed=$count_trim skipped=$count_skip errors=$count_err"
