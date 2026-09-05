#!/usr/bin/env bash
#
# Regenerates the diagrams in docs/ - both the .svg and the .png of each:
#
#   architecture   the whole stack: components, connections, protocols
#   tokenprovider  how the replication TokenProvider plugin works
#
# Each layout lives in docs/<name>.py; edit that, then run this. Rendering
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

for name in architecture tokenprovider; do
  echo "Generating docs/$name.svg..."
  python3 "$ROOT_DIR/docs/$name.py"

  echo "  rasterising to PNG at ${WIDTH}px wide..."
  docker run --rm -v "$ROOT_DIR/docs:/w" -w /w "$IMAGE" \
    rsvg-convert -w "$WIDTH" -o "$name.png" "$name.svg"
done

echo
echo "Done:"
ls -lh "$ROOT_DIR"/docs/*.svg "$ROOT_DIR"/docs/*.png | awk '{print "  " $9 "  " $5}'
