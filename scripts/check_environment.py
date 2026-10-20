"""Validate uv environment, exact lock synchronization and the shared CPU profile."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flbench.environment import (configure_cpu_runtime, environment_errors,
                                environment_policy_errors, environment_snapshot)
from flbench.repository import find_root


def main():
    root = find_root()
    errors = environment_policy_errors(root) + environment_errors(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    configure_cpu_runtime(root, seed=20261020)
    import torch

    report = environment_snapshot(root)
    report.update(device="cpu", torch_cuda_build=torch.version.cuda,
                  torch_num_threads=torch.get_num_threads(),
                  torch_num_interop_threads=torch.get_num_interop_threads(),
                  deterministic_algorithms=torch.are_deterministic_algorithms_enabled())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
