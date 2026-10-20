"""Run the corresponding flbench collaboration command from the source checkout."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flbench.cli import main

if __name__ == "__main__":
    raise SystemExit(main(['publish-run', *sys.argv[1:]]))
