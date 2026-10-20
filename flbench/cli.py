"""Only implemented collaboration commands are exposed here."""

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flbench.environment import environment_errors, environment_snapshot
from flbench.leaderboard import synchronize
from flbench.records import publish_record, validate_record
from flbench.repository import (CONFIG, COST, MANIFEST, OWNERS, check_repository, file_hash,
                                find_root, load_json, protocol_hash, readiness_errors)


def new_record(root: Path, args) -> Path:
    config_path = (root / args.config).resolve()
    if not config_path.is_relative_to(root) or not config_path.is_file():
        raise ValueError("Config must be an existing file inside the repository.")
    load_json(config_path)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
    if dirty.strip():
        raise ValueError("Commit research code/config before creating a run; working tree is dirty.")
    now = datetime.now(timezone.utc)
    run_id = f"{args.owner}-{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}".lower()
    config = load_json(root / CONFIG)
    record = {
        "schema_version": 1, "run_id": run_id, "created_at": now.isoformat(),
        "owner": args.owner, "method_id": args.method, "parent_method": args.parent_method,
        "hypothesis_id": args.hypothesis, "supersedes": None, "git_commit": commit,
        "protocol_hash": protocol_hash(root), "data_hash": load_json(root / MANIFEST)["content_sha256"],
        "config_hash": file_hash(config_path), "cost_hash": file_hash(root / COST),
        "scenario": config["evaluation"]["primary_scenario"], "seed": args.seed,
        "stage": "development", "evaluation_scope": "search_validation", "fidelity": "smoke",
        "budget_sim_seconds": config["evaluation"]["budget_sim_seconds"], "status": "planned",
        "mean_client_macro_f1": None, "j_dev": None, "sim_seconds_used": None, "wall_seconds": None, "up_bytes": None,
        "down_bytes": None, "completed_rounds": None, "artifact_uri": None,
        "artifact_sha256": None, "environment": environment_snapshot(root), "error": None,
    }
    validate_record(record, terminal=False)
    destination = root / "artifacts" / run_id / "record.json"
    destination.parent.mkdir(parents=True, exist_ok=False)
    destination.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="EdgeFL collaboration tools; real-data validation: scripts/validate_pipeline.py.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check", help="Validate scaffold; readiness is a separate check.")
    check.add_argument("--require-ready", action="store_true")
    subparsers.add_parser("protocol", help="Show protocol fingerprint, budget and blockers.")
    sync = subparsers.add_parser("sync-leaderboard", help="Rebuild views from local published records.")
    sync.add_argument("--check", action="store_true", help="Report stale views without writing.")
    new = subparsers.add_parser("new-run", help="Create an unmeasured, ignored local run draft.")
    new.add_argument("--owner", choices=OWNERS, required=True)
    new.add_argument("--method", required=True)
    new.add_argument("--config", required=True)
    new.add_argument("--hypothesis")
    new.add_argument("--parent-method")
    new.add_argument("--seed", type=int, default=11)
    publish = subparsers.add_parser("publish-run", help="Publish one immutable terminal summary.")
    publish.add_argument("record", type=Path)
    args = parser.parse_args(argv)
    try:
        root = find_root()
        if args.command == "check":
            errors = check_repository(root, require_ready=args.require_ready)
            # Also validate run semantics and ensure all generated views are consistent.
            changed = synchronize(root, check=True)
            errors.extend(f"Stale generated view: {name}" for name in changed)
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            if not errors:
                print("Scaffold checks passed. This does not validate model training.")
            return 1 if errors else 0
        if args.command == "protocol":
            config = load_json(root / CONFIG)
            print(json.dumps({"version": config["protocol_version"], "status": config["status"],
                              "protocol_hash": protocol_hash(root), "cost_hash": file_hash(root / COST),
                              "budget_sim_seconds": config["evaluation"]["budget_sim_seconds"],
                              "readiness_blockers": readiness_errors(root)}, indent=2))
        elif args.command == "sync-leaderboard":
            changed = synchronize(root, check=args.check)
            print("\n".join(changed) if changed else "Generated views are up to date.")
            return 1 if args.check and changed else 0
        elif args.command == "new-run":
            errors = environment_errors(root)
            if errors:
                raise ValueError("Environment is not aligned: " + "; ".join(errors))
            print(new_record(root, args))
        elif args.command == "publish-run":
            record = load_json(args.record.resolve())
            print(publish_record(root, record))
            print("Rebuild local views with: uv run --locked --exact python scripts/sync_leaderboard.py")
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
