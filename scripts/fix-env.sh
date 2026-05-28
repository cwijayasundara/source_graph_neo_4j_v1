#!/usr/bin/env bash
# Repair the project after some external tool (sync/backup) hides files
# or creates "* 2" duplicates that break Python's editable install.
#
# Symptoms it fixes:
#   - `uv run ccg ...` -> ModuleNotFoundError: No module named 'code_context_graph'
#   - 21+ "* 2.py" / "* 2.tsx" files in src/ tests/ web/
#   - Ghost ".venv/lib 2/" directory
#
# Run from the repo root: ./scripts/fix-env.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Removing stale '* 2*' duplicates in source tree..."
find . -name "* 2*" \
    -not -path "./.venv/*" \
    -not -path "*/node_modules/*" \
    -not -path "*/.next/*" \
    -not -path "*/source_code_to_analyse/*" \
    -not -path "./.git/*" \
    -type f -delete

echo "Removing stale '* 2*' files from .git/objects..."
find .git/objects -name "* 2*" -type f -delete 2>/dev/null || true

echo "Removing ghost '.venv/lib 2' directories..."
[ -d ".venv/lib 2" ] && rm -rf ".venv/lib 2" || true

echo "Clearing macOS 'hidden' flag on venv files..."
[ -d .venv ] && chflags -R nohidden .venv || true

echo "Reinstalling editable install..."
uv sync

echo "Done. Try: uv run ccg --help"
