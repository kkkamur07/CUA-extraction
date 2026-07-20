"""Thin wrapper so the workbench can invoke the OpenCUA action reduction the
same way as the other processing scripts. See src/cursor/reduce/opencua.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cursor.cli.cli import main  # noqa: E402

if __name__ == "__main__":
    main(["reduce-actions", *sys.argv[1:]])
