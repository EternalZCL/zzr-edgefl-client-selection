"""Preregistration, measured cost calibration and deterministic campaign planning."""

import argparse
import copy
import math
import platform
import statistics
import subprocess
import time
from pathlib import Path

from flbench.environment import configure_cpu_runtime, environment_errors, environment_snapshot
from flbench.repository import CONFIG, COST, file_hash, find_root, load_json, protocol_hash
from flbench.research import load_policy, source_commit, write_json
from flbench.records import published_records

PRESETS = "configs/baselines/presets"
CANDIDATES = "agents/ghj/configs/candidates"
BASELINE_FAMILIES = ["fedavg_u_uniform", "fedprox_u_uniform", "scaffold_uniform",
                     "fedavg_u_round_robin", "fedavg_u_fast_random", "fedavg_u_oort"]
SEARCH_ID = "dev-search-v2"


def initialize(root):
    """Write all settings before profiling/search, including all candidate ablations."""
    methods = []
    def add(stem, method):
        path = f"{PRESETS}/{stem}.json"
        write_json(root / path, method)
        methods.append(path)
    add("uniform", {"method_id": "fedavg_u_uniform", "selector": "uniform"})
    add("round_robin", {"method_id": "fedavg_u_round_robin", "selector": "round_robin"})
    for mu in (0, 0.001, 0.01, 0.1, 1):
        add(f"fedprox-{mu}", {"method_id": "fedprox_u_uniform", "selector": "uniform", "proximal_mu": mu})
    for eta in (0.5, 1):
        add(f"scaffold-{eta}", {"method_id": "scaffold_uniform", "selector": "uniform", "scaffold": True,
                                 "server_learning_rate": eta})
    for exploration in (0, 0.2, 0.5, 1):
        add(f"fast-{exploration}", {"method_id": "fedavg_u_fast_random", "selector": "fast_random",
                                     "selector_config": {"exploration": exploration}})
    for exploration in (0.1, 0.3):
        for window in (5, 10):
            for utility in ("normalized", "original"):
                add(f"oort-{exploration}-{window}-{utility}", {"method_id": "fedavg_u_oort", "selector": "oort",
                    "selector_config": {"exploration": exploration, "pacer_window": window, "utility": utility}})
    candidate_paths = []
    for slots in (1, 2):
        for wait in (0.05, 0.1, 0.2):
            stem = f"coverage-{slots}-{wait}"
            config = {"method_id": "ghj_coverage", "selector": "ghj_coverage",
                      "parent_method": "fedavg_u_fast_random", "hypothesis_id": "ghj-h001",
                      "selector_config": {"exploration": 0.2, "coverage_slots": slots, "wait_fraction": wait}}
            path = f"{CANDIDATES}/{stem}.json"
            write_json(root / path, config)
            candidate_paths.append(path)
            for ablation in ("no_wait", "no_speed"):
                altered = copy.deepcopy(config)
                altered["method_id"] = "ghj_coverage_" + ablation
                altered["selector_config"]["ablation"] = ablation
                write_json(root / f"{CANDIDATES}/{stem}-{ablation}.json", altered)
    write_json(root / f"{PRESETS}/weighted.json", {"method_id": "fedavg_sample_weighted", "selector": "uniform",
                                                 "sample_weighted": True})
    for reference in ("local_only", "centralized"):
        write_json(root / f"{PRESETS}/{reference}.json", {"method_id": reference, "reference": reference})
    write_json(root / "agents/ghj/configs/search.json", {
        "owner": "ghj", "hypothesis_id": "ghj-h001", "status": "preregistered_before_search",
        "baseline_configurations": methods, "candidate_configurations": candidate_paths,
        "primary_scenario": "natural_heterogeneous", "development_seeds": [11, 22, 33],
        "selection_rule": "Highest mean full-B open-validation Macro-F1 within each baseline family; ties prefer listed order. Candidate within minimum delta of best prefers fewer coverage slots then larger wait fraction.",
        "confirmation_rule": "One fixed candidate plus strongest selected baseline, seeds 11/22/33, confirmation once; no retuning from confirmation.",
        "final_rule": "Always evaluate the frozen candidate, even if it loses; 175 core tests with seeds 101..105.",
        "profiling_rule": "LR 0.01/0.03/0.1/0.3 at 100/200/400 rounds, three dev seeds; choose shared LR at 200 rounds; B is mean 200-round heterogeneous Uniform time; delta=max(0.005, baseline seed SD/sqrt(3)).",
        "limitations": "Oort adaptation is documented, not an exact reproduction. Local freeze does not claim team review or automatic Champion promotion."})


def profile(root):
    """Measure all coefficients and LR pilots before freezing any candidate search."""
    import torch
    from baselines.uniform import UniformPolicy
    from benchmark.accounting import encode_message, decode_message
    from benchmark.data import load_prepared
    from benchmark.interfaces import BudgetState, ClientHistory, RoundFeedback
    from benchmark.model import build_model
    from benchmark.simulator import client_metadata, run_experiment, scaffold_controls
    from benchmark.trainer import aggregate_equal, train_local

    code_commit = source_commit(root)
    config, costs = load_json(root / CONFIG), load_json(root / COST)
    if config["status"] == "frozen":
        raise ValueError("Calibrating an already frozen protocol requires a new version.")
    configure_cpu_runtime(root, 11)
    dataset = load_prepared(root, scenario="natural_heterogeneous", seed=11)
    model = build_model(config)
    step_samples, control_samples, server_samples, control_server = [], [], [], []
    for client in sorted(dataset.train)[::3]:
        for repeat in range(3):
            current = copy.deepcopy(model)
            generator = torch.Generator().manual_seed(80000 + client * 10 + repeat)
            train_local(current, dataset.train[client], generator, config)
            step_samples += train_local(current, dataset.train[client], generator, config)["step_seconds"]
            zeros = {k: torch.zeros_like(v) for k, v in current.state_dict().items()}
            control_samples += train_local(current, dataset.train[client], generator, config,
                                           server_control=zeros, client_control=zeros)["step_seconds"]
    state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    for _ in range(60):
        started = time.perf_counter()
        updates = []
        for client in range(6):
            received = decode_message(encode_message(state, {"client_id": client, "role": "download"}))
            updates.append(decode_message(encode_message(received["state_dict"],
                                                        {"client_id": client, "role": "upload", "loss": 0.1, "loss_rms": 0.2, "steps": 4}))["state_dict"])
        aggregate_equal(updates)
        server_samples.append(time.perf_counter() - started)
        started = time.perf_counter()
        for _ in range(6):
            scaffold_controls(state, state, state, state, 4, 0.03)
        aggregate_equal([state] * 6)
        control_server.append(time.perf_counter() - started)
    costs.update(version="cost-v1-ghj-cpu", status="calibrated",
                 reference_hardware={"processor": platform.processor(), **environment_snapshot(root)},
                 reference_train_step_seconds=statistics.median(step_samples),
                 scaffold_train_step_seconds=statistics.median(control_samples),
                 server_round_seconds=statistics.median(server_samples),
                 scaffold_server_extra_seconds=statistics.median(control_server),
                 selector_seconds={}, note="Measured reference CPU medians; network and tier multipliers are simulation assumptions. Selector+observe fixed median costs ensure deterministic recovery.")
    infos = client_metadata(config, dataset, 11)
    histories = {c.client_id: ClientHistory(1, 0.1, 1.0 + c.client_id / 30, 1.2 + c.client_id / 30) for c in infos}
    selector_samples = {}
    for name, path in [("uniform", f"{PRESETS}/uniform.json"), ("round_robin", f"{PRESETS}/round_robin.json"),
                       ("fast_random", f"{PRESETS}/fast-0.2.json"), ("oort", f"{PRESETS}/oort-0.3-5-normalized.json"),
                       ("ghj_coverage", f"{CANDIDATES}/coverage-1-0.1.json")]:
        policy, measurements = load_policy(root, load_json(root / path), 11), []
        for _ in range(100):
            started = time.perf_counter()
            policy.select(infos, BudgetState(1, 10), histories, 6)
            policy.observe(RoundFeedback((1, 2, 3, 4, 5, 6), 1.0, {i: 1.0 for i in range(1, 7)}, {i: 1.1 for i in range(1, 7)}))
            measurements.append(time.perf_counter() - started)
        selector_samples[name] = measurements
        costs["selector_seconds"][name] = statistics.median(measurements)
    pilots = []
    for lr in (0.01, 0.03, 0.1, 0.3):
        for seed in config["evaluation"]["development_seeds"]:
            data = load_prepared(root, scenario="natural_heterogeneous", seed=seed)
            settings = copy.deepcopy(config)
            settings["training"]["initial_learning_rate"] = lr
            for rounds in (100, 200, 400):
                result = run_experiment(root, settings, data, UniformPolicy(seed), costs,
                                         seed=seed, max_rounds=rounds, budget_seconds=100000)
                summary = result["summary"]
                pilots.append({"learning_rate": lr, "seed": seed, "rounds": rounds,
                               "mean_client_macro_f1": summary["mean_client_macro_f1"],
                               "sim_seconds_used": summary["sim_seconds_used"], "wall_seconds": summary["wall_seconds"]})
                print(f"PROFILE lr={lr} seed={seed} rounds={rounds} F1={summary['mean_client_macro_f1']:.6f}", flush=True)
    chosen_lr = max((0.01, 0.03, 0.1, 0.3), key=lambda lr: statistics.mean(
        p["mean_client_macro_f1"] for p in pilots if p["learning_rate"] == lr and p["rounds"] == 200))
    chosen = [p for p in pilots if p["learning_rate"] == chosen_lr and p["rounds"] == 200]
    budget = statistics.mean(p["sim_seconds_used"] for p in chosen)
    delta = max(0.005, statistics.stdev(p["mean_client_macro_f1"] for p in chosen) / math.sqrt(3))
    evidence = {"profiling_code_commit": code_commit, "environment": environment_snapshot(root),
                "reference_step_samples": step_samples, "scaffold_step_samples": control_samples,
                "server_samples": server_samples, "scaffold_server_extra_samples": control_server,
                "selector_samples": selector_samples, "pilots": pilots, "selected_learning_rate": chosen_lr,
                "budget_sim_seconds": budget, "minimum_meaningful_delta": delta,
                "rule": load_json(root / "agents/ghj/configs/search.json")["profiling_rule"],
                "scope": "open_validation_only; not a final result", "cost_coefficients": copy.deepcopy(costs)}
    evidence_path = root / "docs/validation/ghj-research-profile.json"
    write_json(evidence_path, evidence)
    costs.update(evidence_uri=evidence_path.relative_to(root).as_posix(), evidence_sha256=file_hash(evidence_path))
    write_json(root / COST, costs)
    config.update(protocol_version="hapt-v2-ghj-cpu", status="frozen", phase="development")
    config["training"]["initial_learning_rate"] = chosen_lr
    config["evaluation"].update(budget_sim_seconds=budget, minimum_meaningful_delta=delta,
                                curve_budget_fractions=[0.25, 0.5, 0.75, 1.0])
    write_json(root / CONFIG, config)
    print(f"CALIBRATED lr={chosen_lr} B={budget:.9f} delta={delta:.6f}", flush=True)


def freeze_campaign(root, campaign_id, stage, rows, *, code_commit=None, kind="development", candidate=None):
    matrix = [(r["config"], r["scenario"], r["seed"]) for r in rows]
    if len(matrix) != len(set(matrix)):
        raise ValueError("Duplicate rows in a frozen campaign.")
    commit = source_commit(root, code_commit)
    configs = sorted({row["config"] for row in rows})
    spec = {"status": "frozen", "campaign_id": campaign_id, "kind": kind, "stage": stage,
            "protocol_hash": protocol_hash(root), "code_commit": commit,
            "planned_runs": len(rows), "frozen_run_matrix": rows,
            "budget_sim_seconds": load_json(root / CONFIG)["evaluation"]["budget_sim_seconds"],
            "config_hashes": {p: file_hash(root / p) for p in configs},
            "candidate_config_hash": file_hash(root / candidate) if candidate else None}
    destination = root / f"configs/final/{campaign_id}.json"
    if destination.exists():
        if load_json(destination) != spec:
            raise ValueError("Refusing to overwrite an existing preregistration.")
        return destination
    write_json(destination, spec)
    return destination


def register_search(root):
    search = load_json(root / "agents/ghj/configs/search.json")
    rows = [{"config": p, "scenario": "natural_heterogeneous", "seed": seed}
            for p in search["baseline_configurations"] + search["candidate_configurations"]
            for seed in search["development_seeds"]]
    print(freeze_campaign(root, SEARCH_ID, "development", rows))


def select(root):
    search = load_json(root / "agents/ghj/configs/search.json")
    frozen = load_json(root / f"configs/final/{SEARCH_ID}.json")
    all_runs = published_records(root)
    evidence = []
    for path in search["baseline_configurations"] + search["candidate_configurations"]:
        digest = file_hash(root / path)
        runs = [r for r in all_runs if r["protocol_hash"] == frozen["protocol_hash"]
                and r["git_commit"] == frozen["code_commit"] and r["config_hash"] == digest
                and r["scenario"] == "natural_heterogeneous" and r["stage"] == "development"]
        if sorted(r["seed"] for r in runs) != sorted(search["development_seeds"]) or any(r["status"] != "complete" for r in runs):
            raise ValueError("Incomplete or duplicated paired selection evidence: " + path)
        evidence.append({"config": path, "method_id": load_json(root / path)["method_id"],
                         "mean": statistics.mean(r["j_dev"] for r in runs),
                         "sd": statistics.stdev(r["j_dev"] for r in runs), "run_ids": [r["run_id"] for r in runs],
                         "scores_by_seed": {r["seed"]: r["j_dev"] for r in runs}})
    selected = [max((e for e in evidence if e["method_id"] == family), key=lambda e: e["mean"])
                for family in BASELINE_FAMILIES]
    candidates = [e for e in evidence if e["method_id"] == "ghj_coverage"]
    best = max(e["mean"] for e in candidates)
    delta = load_json(root / CONFIG)["evaluation"]["minimum_meaningful_delta"]
    tied = [e for e in candidates if e["mean"] >= best - delta]
    def simplicity(e):
        settings = load_json(root / e["config"])["selector_config"]
        return settings["coverage_slots"], -settings["wait_fraction"]
    candidate = min(tied, key=simplicity)
    strongest = max(selected, key=lambda e: e["mean"])
    selection = {"status": "candidate_frozen_before_confirmation", "code_commit": frozen["code_commit"],
                 "protocol_hash": frozen["protocol_hash"], "baseline_selection": selected, "candidate": candidate,
                 "strongest_baseline": strongest, "all_search_results": evidence,
                 "candidate_advantage": candidate["mean"] - strongest["mean"], "delta": delta,
                 "no_retuning_after_confirmation": True, "team_review": "pending; no Champion promotion performed"}
    destination = root / "agents/ghj/SELECTION.json"
    if destination.exists() and load_json(destination) != selection:
        raise ValueError("Candidate selection was already frozen.")
    write_json(destination, selection)
    paths = [e["config"] for e in selected] + [candidate["config"]]
    config = load_json(root / CONFIG)
    rows = [{"config": p, "scenario": scenario, "seed": seed} for p in paths
            for scenario in config["scenarios"] if scenario != "natural_heterogeneous"
            for seed in search["development_seeds"]]
    print(freeze_campaign(root, "dev-conditions-v2", "development", rows,
                          code_commit=frozen["code_commit"], candidate=candidate["config"]))
    rows = [{"config": p, "scenario": "natural_heterogeneous", "seed": seed}
            for p in [candidate["config"], strongest["config"]] for seed in search["development_seeds"]]
    print(freeze_campaign(root, "confirmation-v2", "confirmation", rows,
                          code_commit=frozen["code_commit"], candidate=candidate["config"]))


def final(root):
    selected = load_json(root / "agents/ghj/SELECTION.json")
    confirmation = load_json(root / "configs/final/confirmation-v2.json")
    records = {r["run_id"]: r for r in published_records(root)}
    for index in range(confirmation["planned_runs"]):
        record = records.get(f"ghj-confirmation-v2-{index + 1:03d}")
        if not record or record["status"] != "complete":
            raise ValueError("The one-shot confirmation campaign is incomplete.")
    config = load_json(root / CONFIG)
    candidate = selected["candidate"]["config"]
    paths = [e["config"] for e in selected["baseline_selection"]] + [candidate]
    seeds = config["evaluation"]["final_seeds"]
    rows = [{"config": p, "scenario": scenario, "seed": seed} for p in paths
            for scenario in config["scenarios"] for seed in seeds]
    rows += [{"config": f"{PRESETS}/{reference}.json", "scenario": scenario, "seed": seed}
             for reference in ("local_only", "centralized")
             for scenario in ("natural_homogeneous", "near_iid_homogeneous") for seed in seeds]
    rows += [{"config": candidate.replace(".json", f"-{ablation}.json"),
              "scenario": "natural_heterogeneous", "seed": seed}
             for ablation in ("no_wait", "no_speed") for seed in seeds]
    rows += [{"config": f"{PRESETS}/weighted.json", "scenario": "natural_heterogeneous", "seed": seed} for seed in seeds]
    if len(rows) != 175:
        raise ValueError("Core matrix must contain exactly 175 distinct runs.")
    print(freeze_campaign(root, "core-final-v2", "test", rows, kind="core",
                          code_commit=selected["code_commit"], candidate=candidate))


def recalibrate_overheads(root):
    """Correct omitted optimizer/serialization overheads before reserved evaluation."""
    import torch
    from benchmark.accounting import encode_message, decode_message
    from benchmark.data import load_prepared
    from benchmark.model import build_model
    from benchmark.trainer import train_local, aggregate_equal
    from benchmark.simulator import scaffold_controls

    commit = source_commit(root)
    config, costs = load_json(root / CONFIG), load_json(root / COST)
    if config["protocol_version"] != "hapt-v2-ghj-cpu":
        raise ValueError("This explicit migration only applies to the retained v2 calibration.")
    configure_cpu_runtime(root, 11)
    dataset = load_prepared(root, scenario="natural_heterogeneous", seed=11)
    model = build_model(config)
    proximal_samples = {}
    for mu in (0.001, 0.01, 0.1, 1.0):
        measurements = []
        for client in sorted(dataset.train)[::3]:
            generator = torch.Generator().manual_seed(90000 + client)
            current = copy.deepcopy(model)
            train_local(current, dataset.train[client], generator, config, proximal_mu=mu)
            for _ in range(3):
                measurements += train_local(current, dataset.train[client], generator, config,
                                            proximal_mu=mu)["step_seconds"]
        proximal_samples[str(mu)] = measurements
    state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    zero = {k: torch.zeros_like(v) for k, v in state.items()}
    larger = {**state, **{"control::" + k: v for k, v in zero.items()}}
    server_samples, deltas = [], []
    for _ in range(60):
        started = time.perf_counter()
        updates = []
        for client in range(6):
            received = decode_message(encode_message(larger, {"client_id": client, "role": "download"}))
            updated, delta = scaffold_controls(state, state, zero, zero, 4,
                                               config["training"]["initial_learning_rate"])
            upload = {**state, **{"control::" + k: v for k, v in delta.items()}}
            decoded = decode_message(encode_message(upload, {"client_id": client, "role": "upload",
                                                            "loss": 0.1, "loss_rms": 0.2, "steps": 4}))
            updates.append({k: decoded["state_dict"][k] for k in state})
        aggregate_equal(updates)
        aggregate_equal([zero] * 6)
        server_samples.append(time.perf_counter() - started)
        deltas.append(max(0.0, server_samples[-1] - costs["server_round_seconds"]))
    costs["fedprox_train_step_seconds"] = {k: max(costs["reference_train_step_seconds"], statistics.median(v))
                                           for k, v in proximal_samples.items()}
    costs["scaffold_server_extra_seconds"] = statistics.median(deltas)
    costs["scaffold_train_step_seconds"] = max(costs["reference_train_step_seconds"], costs["scaffold_train_step_seconds"])
    evidence = {"profiling_code_commit": commit, "correction": "Explicit FedProx per-mu training cost and SCAFFOLD extra tensor serialization/control server cost; applied before confirmation or test.",
                "parent_profile": "docs/validation/ghj-research-profile.json",
                "parent_profile_sha256": file_hash(root / "docs/validation/ghj-research-profile.json"),
                "fedprox_step_samples": proximal_samples, "scaffold_total_server_samples": server_samples,
                "scaffold_extra_server_samples": deltas, "cost_coefficients": copy.deepcopy(costs),
                "baseline_B_and_learning_rate_unchanged": True,
                "old_campaign": "dev-search-v1", "old_results_retained_not_compared": True}
    path = root / "docs/validation/ghj-overheads-v2.json"
    write_json(path, evidence)
    costs.update(version="cost-v2-ghj-all-optimizers", evidence_uri=path.relative_to(root).as_posix(),
                 evidence_sha256=file_hash(path))
    write_json(root / COST, costs)
    config["protocol_version"] = "hapt-v3-ghj-costs"
    write_json(root / CONFIG, config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["initialize", "profile", "recalibrate-overheads", "register-search", "select", "freeze-final"])
    args = parser.parse_args()
    root = find_root()
    errors = environment_errors(root)
    if errors:
        raise ValueError("Environment mismatch: " + "; ".join(errors))
    configure_cpu_runtime(root, 11)
    {"initialize": initialize, "profile": profile, "register-search": register_search,
     "recalibrate-overheads": recalibrate_overheads, "select": select, "freeze-final": final}[args.command](root)


if __name__ == "__main__":
    main()
