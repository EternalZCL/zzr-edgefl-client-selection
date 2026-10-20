"""Download/audit raw HAPT data and construct disjoint normalized feature caches."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flbench.environment import configure_cpu_runtime
from flbench.repository import find_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Require the existing pinned archive.")
    args = parser.parse_args()
    root = find_root()
    configure_cpu_runtime(root, seed=20261020)
    from benchmark.data import prepare_data

    manifest = prepare_data(root, download=not args.offline)
    print(json.dumps({"status": manifest["status"], "clients": len(manifest["clients"]),
                      "total_windows": manifest["total_windows"],
                      "overlap_audit_passed": manifest["overlap_audit_passed"],
                      "content_sha256": manifest["content_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
