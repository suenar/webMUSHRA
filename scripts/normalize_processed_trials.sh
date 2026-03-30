#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-configs/resources/audio/violin-valle-processed}"
MAX_DUR="${MAX_DUR:-11.90}"

if ! command -v ffprobe >/dev/null 2>&1 || ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Need ffprobe + ffmpeg on PATH" >&2
  exit 1
fi

normalize_trial() {
  local dir="$1"
  local ref="$dir/reference.mp3"
  [[ -f "$ref" ]] || { echo "Skip $dir (no reference.mp3)"; return; }

  local sr ch ref_d target
  sr="$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$ref" | tr -d ' \r\n')"
  ch="$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$ref" | tr -d ' \r\n')"
  ref_d="$(ffprobe -v error -select_streams a:0 -show_entries stream=duration -of csv=p=0 "$ref" | tr -d ' \r\n')"

  target="$(awk -v r="$ref_d" -v m="$MAX_DUR" 'BEGIN{ if (r+0 < m+0) printf "%.6f", r+0; else printf "%.6f", m+0 }')"

  echo "--- $(basename "$dir") target=${target}s sr=${sr} ch=${ch}"

  local f tmp
  for f in "$dir"/*.mp3; do
    [[ -f "$f" ]] || continue
    tmp="${f%.mp3}.norm.$$.mp3"
    # Normalize all files in trial to same target length, sr/ch.
    # - atrim enforces max length
    # - apad fills shorter files with silence to target
    # - -t target ensures exact export duration target
    ffmpeg -y -hide_banner -loglevel error -i "$f" \
      -af "atrim=0:${target},apad=pad_dur=${target}" -t "$target" \
      -ar "$sr" -ac "$ch" -c:a libmp3lame -b:a 128k -write_xing 0 -f mp3 "$tmp"
    mv "$tmp" "$f"
  done
}

for d in "$ROOT"/trial_*; do
  [[ -d "$d" ]] || continue
  normalize_trial "$d"
done

echo "Normalization complete."
