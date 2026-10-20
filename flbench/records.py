"""Immutable terminal records with strict types and evaluation-stage boundaries."""

import json
import re
from pathlib import Path

from flbench.repository import OWNERS, finite_number, load_json

SCOPES = {"development": "search_validation", "confirmation": "confirmation_validation",
          "test": "final_test"}
TERMINAL = {"complete", "failed", "timeout", "invalid"}
FIELDS = {
    "schema_version", "run_id", "created_at", "owner", "method_id", "parent_method",
    "hypothesis_id", "supersedes", "git_commit", "protocol_hash", "data_hash", "config_hash",
    "cost_hash", "scenario", "seed", "stage", "evaluation_scope", "fidelity",
    "budget_sim_seconds", "status", "mean_client_macro_f1", "j_dev", "sim_seconds_used", "wall_seconds", "up_bytes",
    "down_bytes", "completed_rounds", "artifact_uri", "artifact_sha256", "environment", "error",
}
HASH_FIELDS = {"protocol_hash", "data_hash", "config_hash", "cost_hash", "artifact_sha256"}
TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]{0,119}\Z")


def validate_record(record: dict, *, terminal: bool = True) -> None:
    if not isinstance(record, dict):
        raise ValueError("Record must be a JSON object.")
    missing, extra = FIELDS - record.keys(), record.keys() - FIELDS
    if missing or extra:
        raise ValueError(f"Record fields mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise ValueError("Unsupported record schema version.")
    for field in ("run_id", "method_id", "scenario"):
        if not isinstance(record[field], str) or not TOKEN.fullmatch(record[field]):
            raise ValueError(f"Invalid {field}: use lowercase letters, digits, dots, underscores, hyphens.")
    if record["owner"] not in OWNERS:
        raise ValueError("Unknown workspace owner.")
    if not isinstance(record["created_at"], str) or not record["created_at"].strip():
        raise ValueError("created_at must be a non-empty ISO timestamp.")
    for field in ("parent_method", "hypothesis_id", "supersedes", "artifact_uri", "error"):
        if record[field] is not None and (
                not isinstance(record[field], str) or not record[field].strip()):
            raise ValueError(f"{field} must be null or a non-empty string.")
    for field in HASH_FIELDS | {"git_commit"}:
        value = record[field]
        width = 40 if field == "git_commit" else 64
        if value is not None and (not isinstance(value, str)
                                  or not re.fullmatch(rf"[0-9a-f]{{{width}}}", value)):
            raise ValueError(f"{field} must be null or a {width}-character lowercase hex hash.")
    if record["stage"] not in SCOPES or record["evaluation_scope"] != SCOPES[record["stage"]]:
        raise ValueError("Evaluation scope does not match its stage.")
    if record["fidelity"] not in {"smoke", "partial", "full"}:
        raise ValueError("Unknown fidelity.")
    statuses = TERMINAL if terminal else TERMINAL | {"planned", "running"}
    if record["status"] not in statuses:
        raise ValueError("Publish only terminal records: complete, failed, timeout, invalid.")
    if type(record["seed"]) is not int or record["seed"] < 0:
        raise ValueError("seed must be a non-negative integer.")
    for field in ("budget_sim_seconds", "sim_seconds_used", "wall_seconds", "mean_client_macro_f1", "j_dev"):
        value = record[field]
        if value is not None and not finite_number(value, positive=field == "budget_sim_seconds"):
            raise ValueError(f"{field} must be null or a finite non-negative number (budget > 0).")
    for field in ("mean_client_macro_f1", "j_dev"):
        if record[field] is not None and record[field] > 1:
            raise ValueError("Macro-F1 must be between 0 and 1.")
    if record["stage"] != "development" and record["j_dev"] is not None:
        raise ValueError("Confirmation/test scores must not be stored as development feedback.")
    for field in ("up_bytes", "down_bytes", "completed_rounds"):
        if record[field] is not None and (type(record[field]) is not int or record[field] < 0):
            raise ValueError(f"{field} must be null or a non-negative integer.")
    if (record["sim_seconds_used"] is not None and record["budget_sim_seconds"] is not None
            and record["sim_seconds_used"] > record["budget_sim_seconds"]):
        raise ValueError("Simulated time used exceeds the declared budget.")
    if not isinstance(record["environment"], dict):
        raise ValueError("environment must be an object.")
    if record["status"] == "complete":
        needed = HASH_FIELDS | {"git_commit", "budget_sim_seconds", "sim_seconds_used",
                                "wall_seconds", "up_bytes", "down_bytes", "completed_rounds",
                                "artifact_uri", "mean_client_macro_f1"}
        if record["stage"] == "development":
            needed |= {"j_dev"}
        absent = sorted(field for field in needed if record[field] is None)
        if absent:
            raise ValueError(f"Complete records require real measured values: {absent}")
        if not record["completed_rounds"]:
            raise ValueError("A complete training run must finish at least one round.")
        if any(not isinstance(record["environment"].get(key), str)
               or not record["environment"][key].strip() for key in ("python", "platform")):
            raise ValueError("Complete records require python/platform environment evidence.")
        if record["error"] is not None:
            raise ValueError("A complete record cannot contain an error.")
        if record["stage"] == "development" and record["j_dev"] != record["mean_client_macro_f1"]:
            raise ValueError("Development score must match the measured mean client Macro-F1.")
    elif record["status"] in TERMINAL:
        if not record["error"]:
            raise ValueError("Failed/timeout/invalid records require a reason.")
        if record["j_dev"] is not None or record["mean_client_macro_f1"] is not None:
            raise ValueError("Non-complete records must not report a ranked score.")


def published_records(root: Path) -> list[dict]:
    records, seen = [], set()
    for owner in OWNERS:
        for path in sorted((root / "agents" / owner / "runs").glob("*.json")):
            record = load_json(path)
            try:
                validate_record(record)
                if record["owner"] != owner or path.stem != record["run_id"]:
                    raise ValueError("Filename/owner do not match the record identity.")
                if record["run_id"] in seen:
                    raise ValueError("Duplicate run ID across workspaces.")
            except ValueError as exc:
                raise ValueError(f"{path.relative_to(root)}: {exc}") from exc
            seen.add(record["run_id"])
            records.append(record)
    return sorted(records, key=lambda record: record["run_id"])


def publish_record(root: Path, record: dict) -> Path:
    validate_record(record)
    if record["run_id"] in {item["run_id"] for item in published_records(root)}:
        raise ValueError("run_id already published; create a new run and retain the original.")
    destination = root / "agents" / record["owner"] / "runs" / f"{record['run_id']}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return destination
