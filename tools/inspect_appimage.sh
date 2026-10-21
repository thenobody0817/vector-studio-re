#!/usr/bin/env bash
# Reproduce the reverse engineering of a Vector Studio AppImage.
#
#   ./tools/inspect_appimage.sh path/to/Vector-Studio-x.y.z-linux-x64.AppImage
#
# Produces, next to the AppImage:
#   <out>/squashfs-root/   raw AppImage contents
#   <out>/asar/            the application extracted from app.asar
#   <out>/modules/         the electron bundle split back into its modules
#
# Nothing here modifies the AppImage; everything is read-only extraction.
set -euo pipefail

APPIMAGE="${1:-}"
if [[ -z "$APPIMAGE" || ! -f "$APPIMAGE" ]]; then
	echo "usage: $0 <Vector-Studio AppImage>" >&2
	exit 2
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${2:-$(dirname "$APPIMAGE")/vector-studio-re/extracted}"

echo "==> extracting AppImage into $OUT/squashfs-root"
mkdir -p "$OUT"
(cd "$OUT" && "$APPIMAGE" --appimage-extract >/dev/null)

ASAR="$OUT/squashfs-root/resources/app.asar"
if [[ ! -f "$ASAR" ]]; then
	echo "no app.asar found - is this a Vector Studio build?" >&2
	exit 1
fi

echo "==> extracting app.asar into $OUT/asar"
rm -rf "$OUT/asar"
python3 "$HERE/extract_asar.py" extract "$ASAR" "$OUT/asar"

echo "==> splitting the electron bundle into $OUT/modules"
rm -rf "$OUT/modules"
python3 "$HERE/split_bundle.py" "$OUT/asar/dist-electron/electron/main.js" "$OUT/modules"

echo
echo "done:"
echo "  asar     $OUT/asar"
echo "  modules  $OUT/modules"
echo
echo "next steps:"
echo "  python3 $HERE/re_context.py $OUT/modules/<module> '<symbol>'   # find a symbol"
echo "  python3 $OUT/../tests/e2e_live.py                              # verify against a live app"
