"""Reproducible scientific runs and append-only campaign execution."""

import argparse
import copy
import importlib.util
import json
import subprocess
import time
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from flbench.environment import configure_cpu_runtime, environment_errors, environment_snapshot
from flbench.records import SCOPES, publish_record, published_records
from flbench.repository import CONFIG, COST, MANIFEST, file_hash, find_root, load_json, protocol_hash, readiness_errors


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def load_policy(root, method, seed):
    from baselines.uniform import UniformPolicy
    from baselines.scheduling import RoundRobinPolicy, FastRandomPolicy, OortPolicy

    kind = method.get("selector", "uniform")
    settings = method.get("selector_config", {})
    classes = {"uniform": UniformPolicy, "round_robin": RoundRobinPolicy,
               "fast_random": FastRandomPolicy, "oort": OortPolicy}
    if kind == "ghj_coverage":
        spec = importlib.util.spec_from_file_location("edgefl_agent_ghj", root / "agents/ghj/policy.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Policy(seed=seed, **settings)
    return classes[kind](seed=seed, **settings)


def research_paths(root):
    from flbench.repository import protocol_files
    return [p.relative_to(root).as_posix() for p in protocol_files(root)] + [
        "agents/ghj/policy.py", "scripts/research.py"]


def source_commit(root, expected=None):
    commit = expected or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    result = subprocess.run(["git", "diff", "--exit-code", commit, "--", *research_paths(root)],
                            cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Commit research sources and protocol before scientific runs.")
    tracked = set(subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit], cwd=root, text=True).splitlines())
    if not set(research_paths(root)) <= tracked:
        raise ValueError("Uncommitted research sources cannot be used for scientific evidence.")
    return commit


def _archive(folder):
    destination = folder / "artifacts.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.iterdir()):
            if path.is_file() and path != destination and path.name != "record.json":
                archive.write(path, arcname=path.name)
    return destination


def execute(root, method_path, *, scenario, seed, run_id, stage="development", campaign=None,
            max_rounds=None, fidelity="full", expected_commit=None, dataset=None, environment=None):
    from benchmark.data import load_prepared
    from benchmark.references import run_reference
    from benchmark.simulator import run_experiment

    method_path = (root / method_path).resolve()
    if not method_path.is_relative_to(root):
        raise ValueError("Method config must be inside the repository.")
    method = load_json(method_path)
    commit = source_commit(root, expected_commit)
    relative_method = method_path.relative_to(root).as_posix()
    committed = subprocess.check_output(["git", "show", f"{commit}:{relative_method}"], cwd=root)
    if committed.replace(b"\r\n", b"\n") != method_path.read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("Method configuration differs from its immutable commit.")
    config = copy.deepcopy(load_json(root / CONFIG))
    costs, manifest = load_json(root / COST), load_json(root / MANIFEST)
    if max_rounds is None and readiness_errors(root):
        raise ValueError("Full-budget experiments require a calibrated frozen protocol.")
    if fidelity == "full" and max_rounds is not None:
        raise ValueError("Round-capped runs cannot claim full-budget fidelity.")
    if stage != "development":
        if campaign is None:
            raise ValueError("Reserved-stage experiment requires a campaign.")
        frozen = load_json(campaign)
        allowed = { (row["config"], row["scenario"], row["seed"]) for row in frozen["frozen_run_matrix"] }
        if (relative_method, scenario, seed) not in allowed or frozen["config_hashes"][relative_method] != file_hash(method_path):
            raise ValueError("Run is absent from the frozen reserved-stage matrix.")
    folder = root / "artifacts" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "record.json").exists() or any(r["run_id"] == run_id for r in published_records(root)):
        raise ValueError("Finalized run already exists; use a new run ID.")
    record = {"schema_version": 1, "run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(),
              "owner": "ghj", "method_id": method["method_id"], "parent_method": method.get("parent_method"),
              "hypothesis_id": method.get("hypothesis_id"), "supersedes": None, "git_commit": commit,
              "protocol_hash": protocol_hash(root), "data_hash": manifest["content_sha256"],
              "config_hash": file_hash(method_path), "cost_hash": file_hash(root / COST), "scenario": scenario,
              "seed": seed, "stage": stage, "evaluation_scope": SCOPES[stage], "fidelity": fidelity,
              "budget_sim_seconds": config["evaluation"]["budget_sim_seconds"], "status": "failed",
              "mean_client_macro_f1": None, "j_dev": None, "sim_seconds_used": None, "wall_seconds": None,
              "up_bytes": None, "down_bytes": None, "completed_rounds": None, "artifact_uri": None,
              "artifact_sha256": None, "environment": environment or environment_snapshot(root), "error": None}
    started = time.perf_counter()
    try:
        if dataset is None:
            dataset = load_prepared(root, scenario=scenario, evaluation_stage=stage, seed=seed, campaign=campaign)
        config["training"]["initial_learning_rate"] = method.get("learning_rate", config["training"]["initial_learning_rate"])
        write_json(folder / "configuration.json", {"protocol": config, "costs": costs, "method": method,
                                                  "seed": seed, "scenario": scenario, "stage": stage,
                                                  "code_commit": commit, "protocol_hash": record["protocol_hash"]})
        if method.get("reference"):
            result = run_reference(root, config, dataset, method["reference"], seed=seed)
            import torch
            torch.save(result["state"], folder / "checkpoint.pt")
        else:
            checkpoint = folder / "checkpoint.pt"
            result = run_experiment(root, config, dataset, load_policy(root, method, seed), costs, seed=seed,
                max_rounds=max_rounds, budget_seconds=config["evaluation"]["budget_sim_seconds"],
                proximal_mu=method.get("proximal_mu", 0.0), scaffold=method.get("scaffold", False),
                server_learning_rate=method.get("server_learning_rate", 1.0),
                sample_weighted=method.get("sample_weighted", False), capture_curve=True,
                checkpoint_path=checkpoint, resume_from=checkpoint if checkpoint.exists() else None)
        summary = result["summary"]
        if not method.get("reference") and fidelity == "full" and summary["stop_reason"] != "simulated_budget":
            raise ValueError("Full-budget experiment ended without exhausting the complete-round budget.")
        write_json(folder / "summary.json", summary)
        with (folder / "rounds.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for row in result["state"]["logs"]:
                handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        for key in ("mean_client_macro_f1", "sim_seconds_used", "wall_seconds", "up_bytes", "down_bytes", "completed_rounds"):
            record[key] = summary[key]
        record["status"] = "complete"
        record["j_dev"] = summary["mean_client_macro_f1"] if stage == "development" else None
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["wall_seconds"] = time.perf_counter() - started
        (folder / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
    archive = _archive(folder)
    record["artifact_uri"] = archive.relative_to(root).as_posix()
    record["artifact_sha256"] = file_hash(archive)
    write_json(folder / "record.json", record)
    publish_record(root, record)
    print(json.dumps({"run_id": run_id, "status": record["status"], "method": method["method_id"],
                      "seed": seed, "scenario": scenario, "macro_f1": record["mean_client_macro_f1"],
                      "wall_seconds": record["wall_seconds"], "error": record["error"]}), flush=True)
    return record


def run_campaign(root, path):
    from benchmark.data import load_prepared
    from flbench.leaderboard import synchronize

    spec = load_json(path)
    if spec["status"] != "frozen" or spec["protocol_hash"] != protocol_hash(root):
        raise ValueError("Campaign is not frozen for the current protocol.")
    source_commit(root, spec["code_commit"])
    if len(spec["frozen_run_matrix"]) != spec["planned_runs"]:
        raise ValueError("Campaign count differs from its preregistration.")
    for name, digest in spec["config_hashes"].items():
        if file_hash(root / name) != digest:
            raise ValueError("Campaign method configuration changed.")
    if spec["stage"] == "development" and spec.get("kind") == "core":
        raise ValueError("The final core campaign must use held-out test data.")
    existing = {r["run_id"]: r for r in published_records(root)}
    environment = environment_snapshot(root)
    datasets = {}
    failures = []
    for index, row in enumerate(spec["frozen_run_matrix"]):
        run_id = f"ghj-{spec['campaign_id']}-{index + 1:03d}"
        if run_id in existing:
            previous = existing[run_id]
            if (previous["protocol_hash"] != spec["protocol_hash"] or previous["git_commit"] != spec["code_commit"]
                    or previous["config_hash"] != spec["config_hashes"][row["config"]]
                    or previous["scenario"] != row["scenario"] or previous["seed"] != row["seed"]
                    or previous["stage"] != spec["stage"]):
                raise ValueError("Existing run identity differs from campaign row.")
            if previous["status"] != "complete":
                failures.append(run_id)
            continue
        key = row["scenario"], row["seed"]
        if key not in datasets:
            datasets[key] = load_prepared(root, scenario=row["scenario"], seed=row["seed"],
                                          evaluation_stage=spec["stage"], campaign=path)
        record = execute(root, row["config"], scenario=row["scenario"], seed=row["seed"],
                         run_id=run_id, stage=spec["stage"], campaign=path, expected_commit=spec["code_commit"],
                         dataset=datasets[key], environment=environment)
        if record["status"] != "complete":
            failures.append(run_id)
            # Preserve failure and stop rather than leaking an invalid campaign into more runs.
            break
    synchronize(root)
    if failures:
        raise ValueError("Campaign has retained failed runs: " + ", ".join(failures))
    print(f"Campaign {spec['campaign_id']}: {spec['planned_runs']} complete.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    campaign = sub.add_parser("campaign")
    campaign.add_argument("manifest", type=Path)
    single = sub.add_parser("run")
    single.add_argument("--config", required=True)
    single.add_argument("--scenario", default="natural_heterogeneous")
    single.add_argument("--seed", type=int, default=11)
    single.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    root = find_root()
    errors = environment_errors(root)
    if errors:
        raise ValueError("Environment mismatch: " + "; ".join(errors))
    configure_cpu_runtime(root, 11)
    if args.command == "campaign":
        run_campaign(root, (root / args.manifest).resolve())
    else:
        execute(root, args.config, scenario=args.scenario, seed=args.seed, run_id=args.run_id)


if __name__ == "__main__":
    main()
