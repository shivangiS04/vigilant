#!/usr/bin/env bash
# VIGILANT demo video assembler — Phase 6
#
# Prerequisites:
#   brew install ffmpeg
#   pip install TTS   (Coqui TTS for offline voiceover)
#   OR: set USE_SAY=1 to use macOS built-in 'say' command (no install needed)
#
# Usage:
#   cd /path/to/vigilant
#   bash demo/build.sh
#
# Output:
#   demo/output/vigilant_demo.mp4   (1920×1080, h264, stereo AAC, ≤ 2:40)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

CLIPS="$SCRIPT_DIR/clips"
VOICEOVER="$SCRIPT_DIR/voiceover"
OUTPUT="$SCRIPT_DIR/output"
DOCS="$REPO_ROOT/docs"

mkdir -p "$CLIPS" "$OUTPUT"

VIDEO_SIZE="1920x1080"
FPS=30
FONT_FILE="/System/Library/Fonts/Helvetica.ttc"

# ---------------------------------------------------------------------------
# 1. Generate voiceover audio
# ---------------------------------------------------------------------------

echo ""
echo "=== Step 1: Generating voiceover audio ==="

generate_audio() {
  local scene="$1"   # e.g. s1_problem
  local txt="$VOICEOVER/${scene}.txt"
  local out="$VOICEOVER/${scene}.aiff"

  if [[ -f "$out" ]]; then
    echo "  $scene — already exists, skipping"
    return
  fi

  if [[ "${USE_SAY:-0}" == "1" ]] || command -v say &>/dev/null; then
    # macOS 'say' — fast, no install needed, decent quality
    say --voice="Samantha" --rate=175 \
        --input-file="$txt" \
        --output-file="$out"
    echo "  $scene → $out  (macOS say)"
  else
    # Coqui TTS fallback (needs: pip install TTS)
    python3 -m TTS.bin.synthesize \
      --text "$(cat "$txt")" \
      --model_name "tts_models/en/ljspeech/tacotron2-DDC" \
      --out_path "${out%.aiff}.wav"
    echo "  $scene → ${out%.aiff}.wav  (Coqui TTS)"
  fi
}

for scene in s1_problem s2_dashboard s3_rapid_return s4_architecture \
             s5_feedback s6_caretaking s7_analytics s8_close; do
  generate_audio "$scene"
done

echo "  Audio generation done."

# ---------------------------------------------------------------------------
# 2. Build title cards (scenes 1 and 8) as short video clips
# ---------------------------------------------------------------------------

echo ""
echo "=== Step 2: Rendering title cards ==="

# Scene 1 title card (15 s): dark background, VIGILANT wordmark, tagline
if [[ ! -f "$CLIPS/scene1_title.mp4" ]]; then
  ffmpeg -y \
    -f lavfi -i "color=c=0x1a202c:size=${VIDEO_SIZE}:rate=${FPS}:duration=15" \
    -vf "
      drawtext=fontfile='${FONT_FILE}':text='VIGILANT':
        fontcolor=white:fontsize=96:x=(w-text_w)/2:y=(h-text_h)/2-60:
        enable='between(t,1,15)',
      drawtext=fontfile='${FONT_FILE}':text='Behavioral intelligence for Ring homes':
        fontcolor=0xa0aec0:fontsize=36:x=(w-text_w)/2:y=(h/2)+40:
        enable='between(t,2,15)'
    " \
    -c:v libx264 -preset fast -crf 18 \
    "$CLIPS/scene1_title.mp4"
  echo "  scene1_title.mp4 created"
fi

# Scene 8 close card (10 s): same dark background, repo URL
if [[ ! -f "$CLIPS/scene8_close.mp4" ]]; then
  ffmpeg -y \
    -f lavfi -i "color=c=0x1a202c:size=${VIDEO_SIZE}:rate=${FPS}:duration=10" \
    -vf "
      drawtext=fontfile='${FONT_FILE}':text='VIGILANT':
        fontcolor=white:fontsize=96:x=(w-text_w)/2:y=(h-text_h)/2-60:
        enable='between(t,0,10)',
      drawtext=fontfile='${FONT_FILE}':text='github.com/shivangiS04/vigilant':
        fontcolor=0x63b3ed:fontsize=32:x=(w-text_w)/2:y=(h/2)+40:
        enable='between(t,1,10)',
      drawtext=fontfile='${FONT_FILE}':text='Amazon Developer Hackathon':
        fontcolor=0xa0aec0:fontsize=24:x=(w-text_w)/2:y=(h/2)+90:
        enable='between(t,2,10)'
    " \
    -c:v libx264 -preset fast -crf 18 \
    "$CLIPS/scene8_close.mp4"
  echo "  scene8_close.mp4 created"
fi

# ---------------------------------------------------------------------------
# 3. Convert Playwright webm clips → mp4 (with padding to target duration)
# ---------------------------------------------------------------------------

echo ""
echo "=== Step 3: Converting Playwright clips ==="

# scene, target_duration_seconds
convert_clip() {
  local name="$1"
  local dur="$2"
  local src="$CLIPS/${name}.webm"
  local dst="$CLIPS/${name}.mp4"

  if [[ ! -f "$src" ]]; then
    echo "  WARNING: $src not found — skipping (run npx tsx demo/record.ts first)"
    return
  fi

  if [[ -f "$dst" ]]; then
    echo "  $name.mp4 already exists, skipping"
    return
  fi

  # Trim or pad to target duration, re-encode to consistent h264
  ffmpeg -y -i "$src" \
    -t "$dur" \
    -vf "scale=${VIDEO_SIZE},setsar=1" \
    -r "${FPS}" \
    -c:v libx264 -preset fast -crf 18 \
    -an \
    "$dst"
  echo "  $name.mp4 (${dur}s)"
}

convert_clip scene2_dashboard     25
convert_clip scene3_rapid_return  35
convert_clip scene4_architecture  20
convert_clip scene5_feedback      20
convert_clip scene6_caretaking    20
convert_clip scene7_analytics     15

# ---------------------------------------------------------------------------
# 4. Merge video clips + audio per scene → muxed scene files
# ---------------------------------------------------------------------------

echo ""
echo "=== Step 4: Muxing audio into scene clips ==="

mux_scene() {
  local name="$1"       # e.g. scene2_dashboard
  local audio_key="$2"  # e.g. s2_dashboard
  local out="$CLIPS/${name}_muxed.mp4"

  if [[ -f "$out" ]]; then
    echo "  ${name}_muxed.mp4 already exists, skipping"
    return
  fi

  local video="$CLIPS/${name}.mp4"
  local audio=""
  for ext in aiff wav mp3; do
    if [[ -f "$VOICEOVER/${audio_key}.${ext}" ]]; then
      audio="$VOICEOVER/${audio_key}.${ext}"
      break
    fi
  done

  if [[ -z "$audio" ]]; then
    echo "  WARNING: no audio for $audio_key — using silent clip"
    cp "$video" "$out"
    return
  fi

  ffmpeg -y \
    -i "$video" \
    -i "$audio" \
    -c:v copy \
    -c:a aac -b:a 192k \
    -shortest \
    "$out"
  echo "  ${name}_muxed.mp4"
}

# Title cards already have no audio track from ffmpeg; mux separately
mux_scene scene1_title       s1_problem
mux_scene scene2_dashboard   s2_dashboard
mux_scene scene3_rapid_return s3_rapid_return
mux_scene scene4_architecture s4_architecture
mux_scene scene5_feedback    s5_feedback
mux_scene scene6_caretaking  s6_caretaking
mux_scene scene7_analytics   s7_analytics
mux_scene scene8_close       s8_close

# ---------------------------------------------------------------------------
# 5. Concatenate all muxed scenes into final video
# ---------------------------------------------------------------------------

echo ""
echo "=== Step 5: Concatenating scenes ==="

CONCAT_LIST="$CLIPS/concat_list.txt"
cat > "$CONCAT_LIST" <<EOF
file 'scene1_title_muxed.mp4'
file 'scene2_dashboard_muxed.mp4'
file 'scene3_rapid_return_muxed.mp4'
file 'scene4_architecture_muxed.mp4'
file 'scene5_feedback_muxed.mp4'
file 'scene6_caretaking_muxed.mp4'
file 'scene7_analytics_muxed.mp4'
file 'scene8_close_muxed.mp4'
EOF

ffmpeg -y \
  -f concat -safe 0 -i "$CONCAT_LIST" \
  -c:v libx264 -preset medium -crf 17 \
  -c:a aac -b:a 192k \
  -movflags +faststart \
  "$OUTPUT/vigilant_demo.mp4"

# ---------------------------------------------------------------------------
# 6. Stats
# ---------------------------------------------------------------------------

echo ""
echo "=== Done ==="
DURATION=$(ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 \
  "$OUTPUT/vigilant_demo.mp4" 2>/dev/null | awk '{printf "%d:%02d", $1/60, $1%60}')
SIZE=$(du -sh "$OUTPUT/vigilant_demo.mp4" | cut -f1)

echo ""
echo "  Output : $OUTPUT/vigilant_demo.mp4"
echo "  Runtime: $DURATION"
echo "  Size   : $SIZE"
echo ""
echo "  Submit to: https://developer.amazon.com/alexadevchallenge"
