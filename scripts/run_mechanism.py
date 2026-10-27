"""Preregistered development-only comparison at exactly 100 completed rounds."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flbench.environment import configure_cpu_runtime, environment_errors
from flbench.repository import find_root, load_json
from flbench.research import execute
from flbench.records import published_records
from flbench.leaderboard import synchronize

if __name__ == "__main__":
    root = find_root()
    errors = environment_errors(root)
    if errors:
        raise ValueError(errors)
    configure_cpu_runtime(root, 11)
    selection = load_json(root / "agents/ghj/SELECTION.json")
    paths = [item["config"] for item in selection["baseline_selection"]
             if item["method_id"] in {"fedavg_u_uniform", "fedavg_u_fast_random"}]
    paths.append(selection["candidate"]["config"])
    existing = {r["run_id"] for r in published_records(root)}
    index = 0
    for path in paths:
        for seed in (11, 22, 33):
            index += 1
            run_id = f"ghj-matched-100-v1-{index:03d}"
            if run_id in existing:
                continue
            result = execute(root, path, scenario="natural_heterogeneous", seed=seed, run_id=run_id,
                             max_rounds=100, fidelity="partial", expected_commit=selection["code_commit"])
            if result["status"] != "complete" or result["completed_rounds"] != 100:
                raise ValueError("Matched-round diagnostic did not complete exactly 100 rounds.")
    synchronize(root)
