"""Repository discovery, fingerprints and explicit bootstrap readiness checks."""

import hashlib
import json
import math
from pathlib import Path

OWNERS = ("zzr", "zzw", "ghj", "xyk")
CONFIG = "configs/benchmark/hapt_v1.json"
COST = "configs/system/cost_model.json"
MANIFEST = "data/manifests/hapt_v1.json"


def find_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / CONFIG).is_file() and (candidate / "PROTOCOL.md").is_file():
            return candidate
    raise ValueError("Run this command inside the EdgeFL repository.")


def load_json(path: Path):
    def invalid_constant(value):
        raise ValueError(f"Non-finite JSON constant is forbidden: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol_files(root: Path) -> list[Path]:
    files = [root / "PROTOCOL.md", root / "schemas/run.schema.json", root / "pyproject.toml",
             root / ".python-version", root / "uv.lock",
             root / "benchmark/IMPLEMENTATION_STATUS.json"]
    for folder in ("benchmark", "baselines", "flbench"):
        files.extend((root / folder).glob("*.py"))
    for folder in ("configs/benchmark", "configs/system", "configs/baselines", "configs/environment"):
        files.extend((root / folder).glob("*.json"))
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def protocol_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in protocol_files(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        # Git normalizes these text files to LF. Match across Windows/Linux checkouts.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def finite_number(value, *, positive=False) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def readiness_errors(root: Path) -> list[str]:
    config = load_json(root / CONFIG)
    cost = load_json(root / COST)
    manifest = load_json(root / MANIFEST)
    implementations = load_json(root / "benchmark/IMPLEMENTATION_STATUS.json")
    catalog = load_json(root / "configs/baselines/catalog.json")
    errors = []
    if config["status"] != "frozen":
        errors.append("Protocol is still draft; freeze after profiling and review.")
    if not finite_number(config["evaluation"]["budget_sim_seconds"], positive=True):
        errors.append("Absolute simulated time budget B is not calibrated.")
    if not finite_number(config["evaluation"]["minimum_meaningful_delta"], positive=True):
        errors.append("Minimum meaningful improvement is not preregistered.")
    if (manifest["status"] != "ready" or not manifest["overlap_audit_passed"]
            or not manifest["clients"] or not manifest["source_files"]
            or not isinstance(manifest["content_sha256"], str)
            or len(manifest["content_sha256"]) != 64):
        errors.append("Audited HAPT manifest and overlap evidence are not ready.")
    if (cost["status"] != "calibrated"
            or not finite_number(cost["reference_train_step_seconds"], positive=True)
            or not finite_number(cost["server_round_seconds"])
            or not cost["reference_hardware"] or not cost["evidence_uri"]):
        errors.append("Measured compute/server costs and profiling evidence are missing.")
    if cost.get("evidence_sha256"):
        evidence = (root / cost["evidence_uri"]).resolve()
        if not evidence.is_relative_to(root) or not evidence.is_file() or file_hash(evidence) != cost["evidence_sha256"]:
            errors.append("Cost profiling evidence is missing or its checksum differs.")
    errors.extend(f"Implementation pending: {key}" for key, done in implementations.items()
                  if done is not True)
    errors.extend(f"Baseline pending: {item['method_id']}" for item in catalog["methods"]
                  if item["status"] != "implemented")
    return errors


def check_repository(root: Path, *, require_ready: bool = False) -> list[str]:
    required = ["README.md", "AGENTS.md", "CONTRIBUTING.md", "PROTOCOL.md", "pyproject.toml",
                ".python-version", "uv.lock", "configs/environment/runtime.json",
                "configs/environment/smoke.json", "scripts/check_environment.py",
                "scripts/smoke_train.py", "docs/environment.md",
                "scripts/prepare_data.py", "scripts/validate_pipeline.py",
                "configs/environment/federated_smoke.json", "docs/pipeline-validation.md",
                "docs/project-plan.md", "docs/course-requirements.md", "docs/collaboration.md",
                "docs/experiments.md", "docs/architecture.md", "docs/roadmap.md",
                "schemas/run.schema.json", "shared/OBJECTIVE.md", "shared/HYPOTHESES.md",
                "shared/GLOBAL_STATUS.md", "shared/LEADERBOARD.md", "shared/EXPERIMENT_INDEX.jsonl",
                "shared/CHAMPION_DEV.json", "shared/CHAMPION_FINAL.json", CONFIG, COST, MANIFEST,
                "benchmark/IMPLEMENTATION_STATUS.json", "configs/baselines/catalog.json",
                "configs/final/campaign.draft.json"]
    for owner in OWNERS:
        required.extend(f"agents/{owner}/{name}" for name in (
            "AGENTS.md", "HANDOFF.md", "RESEARCH.md", "policy.py", "configs/search.json",
            "runs/README.md"))
    errors = [f"Missing required file: {name}" for name in required if not (root / name).is_file()]
    if errors:
        return errors
    # Validate every versioned configuration and record schema, not local artifacts or caches.
    folders = ("configs", "schemas", "shared", "data/manifests", "agents", "benchmark")
    for folder in folders:
        for path in sorted((root / folder).rglob("*.json")):
            try:
                load_json(path)
            except (ValueError, OSError) as exc:
                errors.append(f"Invalid JSON in {path.relative_to(root)}: {exc}")
    if errors:
        return errors
    config = load_json(root / CONFIG)
    evaluation = config["evaluation"]
    if config["status"] not in {"draft", "frozen"}:
        errors.append("Protocol status must be draft or frozen.")
    if evaluation["objective"] != "mean_client_macro_f1":
        errors.append("Shared objective must be mean_client_macro_f1.")
    if config["training"]["clients_per_round"] > config["dataset"]["num_clients"]:
        errors.append("More clients selected per round than the total population.")
    for key in ("development_seeds", "final_seeds"):
        seeds = evaluation[key]
        if not seeds or any(type(seed) is not int or seed < 0 for seed in seeds):
            errors.append(f"{key} must contain non-negative integer seeds.")
        elif len(seeds) != len(set(seeds)):
            errors.append(f"{key} contains duplicate seeds.")
    if set(evaluation["development_seeds"]) & set(evaluation["final_seeds"]):
        errors.append("Development and final seeds must be separate.")
    from flbench.environment import environment_policy_errors

    errors.extend(environment_policy_errors(root))
    if require_ready:
        errors.extend(readiness_errors(root))
    return errors
