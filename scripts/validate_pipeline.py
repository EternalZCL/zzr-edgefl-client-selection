"""Short real-HAPT validation of the complete development pipeline and four workspaces."""

import argparse
import copy
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flbench.environment import configure_cpu_runtime, environment_errors, environment_snapshot
from flbench.repository import CONFIG, COST, MANIFEST, OWNERS, file_hash, find_root, load_json, protocol_hash


def load_workspace_policy(root, owner, seed):
    spec = importlib.util.spec_from_file_location(f"edgefl_agent_{owner}", root / "agents" / owner / "policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Policy(seed=seed)


def validate(root, output, *, prepare=False, offline=False):
    errors = environment_errors(root)
    if errors:
        raise ValueError("Environment mismatch: " + "; ".join(errors))
    settings = load_json(root / "configs/environment/federated_smoke.json")
    seed, budget = settings["seed"], settings["diagnostic_budget_sim_seconds"]
    configure_cpu_runtime(root, seed)
    import torch
    from baselines.uniform import UniformPolicy
    from benchmark.data import load_prepared, prepare_data
    from benchmark.simulator import profile_diagnostic_costs, run_experiment

    if prepare:
        prepare_data(root, download=not offline)
    manifest = load_json(root / MANIFEST)
    if manifest["status"] != "ready":
        raise ValueError("Prepare real HAPT data first, or add --prepare.")
    config = load_json(root / CONFIG)
    dataset = load_prepared(root, scenario="natural_heterogeneous", seed=seed)
    output.mkdir(parents=True, exist_ok=True)
    costs = copy.deepcopy(load_json(root / COST))
    profile = profile_diagnostic_costs(config, dataset, seed)
    costs.update(status="smoke_profiled", reference_hardware=environment_snapshot(root),
                 reference_train_step_seconds=profile["reference_train_step_seconds"],
                 server_round_seconds=profile["server_round_seconds"],
                 evidence_uri="artifacts/federated-smoke/report.json",
                 note="Measured short-run engineering profile. Not calibrated/frozen for a research leaderboard.")
    # Keep diagnostics local; never replace the team's uncalibrated/frozen research cost table.
    print("Running real-HAPT FedAvg, 30 clients / 6 selected / 4 local steps...", flush=True)
    common = {"seed": seed, "budget_seconds": budget}
    full = run_experiment(root, config, dataset, UniformPolicy(seed), costs,
                          max_rounds=settings["main_rounds"], checkpoint_path=output / "continuous.pt", **common)
    first = run_experiment(root, config, dataset, UniformPolicy(seed), costs,
                           max_rounds=settings["checkpoint_round"], checkpoint_path=output / "partial.pt", **common)
    resumed = run_experiment(root, config, dataset, UniformPolicy(seed), costs,
                             max_rounds=settings["main_rounds"], resume_from=output / "partial.pt",
                             checkpoint_path=output / "resumed.pt", **common)
    resume_equal = all(torch.equal(value, resumed["state"]["model"][key])
                       for key, value in full["state"]["model"].items())
    trace_equal = full["state"]["logs"] == resumed["state"]["logs"]
    rng_equal = all(torch.equal(value, resumed["state"]["client_rng"][key])
                    for key, value in full["state"]["client_rng"].items())
    scenarios = []
    for scenario in config["scenarios"]:
        if scenario == dataset.scenario:
            scenarios.append(full["summary"])
            continue
        other = load_prepared(root, scenario=scenario, seed=seed)
        scenarios.append(run_experiment(root, config, other, UniformPolicy(seed), costs,
                                         max_rounds=settings["scenario_rounds"], **common)["summary"])
    workspaces = []
    for owner in OWNERS:
        policy = load_workspace_policy(root, owner, seed)
        result = run_experiment(root, config, dataset, policy, costs,
                                max_rounds=settings["workspace_rounds"], **common)
        workspaces.append({"owner": owner, "policy_called_after_warmup":
                           result["summary"]["completed_rounds"] > config["training"]["warmup_rounds"],
                           "summary": result["summary"]})
    prox = run_experiment(root, config, dataset, UniformPolicy(seed), costs,
                          max_rounds=settings["scenario_rounds"], proximal_mu=settings["proximal_mu"], **common)
    stopped = run_experiment(root, config, dataset, UniformPolicy(seed), costs,
                             max_rounds=1, seed=seed, budget_seconds=1e-12)
    crossed = False
    try:
        load_prepared(root, scenario=dataset.scenario, evaluation_stage="test")
    except ValueError:
        crossed = True
    checks = {
        "real_hapt_30_clients": len(dataset.train) == 30,
        "zero_raw_window_overlap": manifest["overlap_audit_passed"],
        "all_clients_have_six_class_train_validation_test_support": all(
            min(item["splits"][split]["class_counts"]) > 0 for item in manifest["clients"]
            for split in ("train", "validation", "test")),
        "search_validation_only_20_clients": len(dataset.validation) == 20,
        "reserved_evaluation_rejected": crossed,
        "main_round_cap_reached": full["summary"]["completed_rounds"] == settings["main_rounds"],
        "all_four_scenarios_ran": len(scenarios) == 4 and all(row["completed_rounds"] > 0 for row in scenarios),
        "all_four_workspace_policies_ran": all(row["policy_called_after_warmup"] for row in workspaces),
        "fedprox_ran": prox["summary"]["completed_rounds"] == settings["scenario_rounds"],
        "checkpoint_weights_exact": resume_equal,
        "checkpoint_selection_time_bytes_trace_exact": trace_equal,
        "checkpoint_client_rng_exact": rng_equal,
        "budget_stops_before_first_local_update": stopped["summary"]["completed_rounds"] == 0
            and stopped["summary"]["training_steps"] == 0 and stopped["summary"]["up_bytes"] == 0,
        "communication_serialization_counted": min(full["summary"]["up_bytes"], full["summary"]["down_bytes"]) > 0,
        "fixed_local_steps_counted": full["summary"]["training_steps"]
            == settings["main_rounds"] * config["training"]["clients_per_round"] * config["training"]["local_steps"],
        "all_clients_participated_in_warmup": all(row["participations"] > 0
                                                  for row in first["state"]["histories"].values())
            if settings["checkpoint_round"] >= config["training"]["warmup_rounds"] else all(
                row["participations"] > 0 for row in full["state"]["histories"].values()),
    }
    report = {"status": "passed" if all(checks.values()) else "failed",
               "purpose": settings["purpose"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "checks": checks, "main_run": full["summary"], "scenarios": scenarios,
               "workspaces": workspaces, "fedprox_run": prox["summary"], "data_total_windows": manifest["total_windows"],
               "source_archive_sha256": manifest["archive_sha256"], "data_hash": manifest["content_sha256"],
               "protocol_hash": protocol_hash(root), "uv_lock_sha256": file_hash(root / "uv.lock"),
               "validation_script_sha256": file_hash(Path(__file__)),
               "source_state": "local_bootstrap_validation_not_a_published_research_run",
               "environment": environment_snapshot(root), "diagnostic_cost_profile": profile,
               "settings": settings,
               "limitations": ["Round-capped development validation, not a converged score or method comparison.",
                                 "Diagnostic simulated budget/costs are not the frozen research B/cost model.",
                                 "SCAFFOLD, Oort and other selection baselines are not validated by this check.",
                                 "Confirmation/final test labels are not evaluated."]}
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "rounds.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                                                  for row in full["state"]["logs"]), encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": checks, "main_run": full["summary"],
                      "report": str(report_path)}, indent=2), flush=True)
    if report["status"] != "passed":
        raise AssertionError("Full pipeline validation failed; inspect its report.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("artifacts/federated-smoke"))
    args = parser.parse_args()
    root = find_root()
    validate(root, (root / args.output).resolve(), prepare=args.prepare, offline=args.offline)


if __name__ == "__main__":
    main()
