#!/usr/bin/env bash
#
# Regenerates docs/architecture.svg and docs/architecture.png.
#
# The layout lives in docs/architecture.py; edit that, then run this. Rendering
# happens inside a throwaway container so nothing has to be installed on the
# host - the only requirements are python3 (to emit the SVG) and Docker (to
# rasterise it).
#
#   ./scripts/render-diagram.sh            # 2660px wide, the checked-in size
#   WIDTH=4000 ./scripts/render-diagram.sh # larger, e.g. for print
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
WIDTH=${WIDTH:-2660}
IMAGE=${RENDER_IMAGE:-xdc-diagram-renderer}

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building the renderer image ($IMAGE)..."
  docker build -t "$IMAGE" - <<'DOCKERFILE'
FROM alpine:latest
RUN apk add --no-cache rsvg-convert ttf-dejavu font-noto
DOCKERFILE
fi

echo "Generating SVG..."
python3 "$ROOT_DIR/docs/architecture.py"

echo "Rasterising to PNG at ${WIDTH}px wide..."
docker run --rm -v "$ROOT_DIR/docs:/w" -w /w "$IMAGE" \
  rsvg-convert -w "$WIDTH" -o architecture.png architecture.svg

echo
echo "Done:"
ls -lh "$ROOT_DIR/docs/architecture.svg" "$ROOT_DIR/docs/architecture.png" | awk '{print "  " $9 "  " $5}'
