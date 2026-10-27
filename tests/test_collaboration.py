"""Synthetic test records live only in temporary directories, never in real leaderboards."""

import argparse
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from baselines.uniform import UniformPolicy
from benchmark.interfaces import BudgetState, ClientInfo
from flbench.cli import new_record
from flbench.environment import environment_policy_errors
from flbench.leaderboard import rank_groups, synchronize
from flbench.records import publish_record, validate_record
from flbench.repository import OWNERS, load_json, protocol_hash, readiness_errors

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "protocol_hash": "a" * 64, "data_hash": "b" * 64, "cost_hash": "d" * 64,
    "budget_sim_seconds": 100, "scenario": "natural_heterogeneous", "stage": "development",
    "evaluation_scope": "search_validation", "fidelity": "full", "seeds": [11, 22, 33],
}


def measured_fixture(seed=11, *, owner="zzr", score=0.7):
    """Fabricated values solely for testing validation and grouping, not scientific evidence."""
    return {
        "schema_version": 1, "run_id": f"{owner}-test-{seed}",
        "created_at": "2026-10-20T00:00:00+00:00", "owner": owner,
        "method_id": "synthetic-test-only", "parent_method": None, "hypothesis_id": "H001",
        "supersedes": None, "git_commit": "1" * 40, "protocol_hash": "a" * 64,
        "data_hash": "b" * 64, "config_hash": "c" * 64, "cost_hash": "d" * 64,
        "scenario": "natural_heterogeneous", "seed": seed, "stage": "development",
        "evaluation_scope": "search_validation", "fidelity": "full", "budget_sim_seconds": 100,
        "status": "complete", "mean_client_macro_f1": score, "j_dev": score,
        "sim_seconds_used": 99, "wall_seconds": 1.5, "up_bytes": 100, "down_bytes": 100,
        "completed_rounds": 10, "artifact_uri": "test-fixture-only://archive",
        "artifact_sha256": "e" * 64, "environment": {"python": "3.11", "platform": "fixture"},
        "error": None,
    }


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.clients = [ClientInfo(index, 20, 1.0) for index in range(30)]
        self.budget = BudgetState(0, 100)

    def test_json_checkpoint_restores_future_selections(self):
        original = UniformPolicy(seed=42)
        original.select(self.clients, self.budget, {}, 6)
        saved = json.loads(json.dumps(original.state_dict()))
        restored = UniformPolicy(seed=999)
        restored.load_state_dict(saved)
        for _ in range(8):
            expected = original.select(self.clients, self.budget, {}, 6)
            self.assertEqual(expected, restored.select(self.clients, self.budget, {}, 6))
            self.assertEqual(len(set(expected)), 6)
            self.assertTrue(set(expected) <= set(range(30)))

    def test_rejects_duplicate_clients_and_impossible_sample(self):
        policy = UniformPolicy()
        for clients, count in [(self.clients[:1] * 2, 1), (self.clients, 31), (self.clients, True)]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                policy.select(clients, self.budget, {}, count)

    def test_all_personal_starters_obey_shared_interface(self):
        for owner in OWNERS:
            spec = importlib.util.spec_from_file_location(owner, ROOT / "agents" / owner / "policy.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(len(module.Policy(seed=1).select(self.clients, self.budget, {}, 6)), 6)


class RecordBoundaryTests(unittest.TestCase):
    def test_rejects_boolean_nonfinite_and_out_of_range_scores(self):
        for score in (True, float("nan"), float("inf"), -0.1, 1.1):
            record = measured_fixture(score=score)
            with self.subTest(score=score), self.assertRaises(ValueError):
                validate_record(record)

    def test_rejects_budget_overrun_and_unmeasured_success(self):
        for field, value in (("sim_seconds_used", 101), ("data_hash", None),
                             ("artifact_sha256", None), ("completed_rounds", 0)):
            record = measured_fixture()
            record[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_record(record)

    def test_confirmation_never_becomes_development_feedback(self):
        record = measured_fixture()
        record.update(stage="confirmation", evaluation_scope="confirmation_validation")
        with self.assertRaises(ValueError):
            validate_record(record)
        record["j_dev"] = None
        validate_record(record)  # General metric retained, dev feedback absent.
        self.assertEqual(rank_groups([record], expected=EXPECTED), [])

    def test_failures_keep_reason_and_do_not_require_invented_measurements(self):
        record = measured_fixture()
        record.update(status="failed", error="synthetic test: data not available",
                      data_hash=None, mean_client_macro_f1=None, j_dev=None,
                      sim_seconds_used=None, artifact_sha256=None)
        validate_record(record)
        record["error"] = None
        with self.assertRaises(ValueError):
            validate_record(record)

    def test_unfinished_records_cannot_be_published(self):
        record = measured_fixture()
        record["status"] = "running"
        with self.assertRaises(ValueError):
            validate_record(record)


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.runs = [measured_fixture(seed, score=score)
                     for seed, score in zip(EXPECTED["seeds"], (0.6, 0.7, 0.8))]

    def test_aggregates_all_registered_seeds(self):
        rows = rank_groups(self.runs, expected=EXPECTED)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["mean"], 0.7)
        self.assertAlmostEqual(rows[0]["sd"], 0.1)

    def test_missing_or_duplicate_seed_cannot_cherry_pick_score(self):
        self.assertEqual(rank_groups(self.runs[:2], expected=EXPECTED), [])
        extra = measured_fixture(11, score=1.0)
        extra["run_id"] = "zzr-extra-test-only"
        self.assertEqual(rank_groups(self.runs + [extra], expected=EXPECTED), [])

    def test_changed_protocol_cost_budget_or_fidelity_never_mix(self):
        for field, value in (("protocol_hash", "f" * 64), ("cost_hash", "f" * 64),
                             ("budget_sim_seconds", 50), ("fidelity", "partial")):
            runs = copy.deepcopy(self.runs)
            runs[0][field] = value
            with self.subTest(field=field):
                self.assertEqual(rank_groups(runs, expected=EXPECTED), [])

    def test_different_implementation_commits_do_not_form_one_group(self):
        self.runs[0]["git_commit"] = "2" * 40
        self.assertEqual(rank_groups(self.runs, expected=EXPECTED), [])


class RepositoryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # find_root() resolves the production root; Windows TEMP can use an 8.3 alias.
        self.root = (Path(self.temporary.name) / "repo").resolve()
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", "artifacts", "*.egg-info", "hapt", "hapt-v1"))
        # Workflow fixtures start empty even after the real repository has published runs.
        for path in self.root.glob("agents/*/runs/*.json"):
            path.unlink()
        synchronize(self.root)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "flbench", *args], cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8")

    def test_bootstrap_cannot_claim_training_readiness(self):
        config_path = self.root / "configs/benchmark/hapt_v1.json"
        config = load_json(config_path)
        config["status"] = "draft"
        config["evaluation"]["budget_sim_seconds"] = None
        config_path.write_text(json.dumps(config), encoding="utf-8")
        synchronize(self.root)
        self.assertTrue(readiness_errors(self.root))
        result = self.cli("check", "--require-ready")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("budget B", result.stderr)

    def test_environment_policy_rejects_changed_python_pin(self):
        (self.root / ".python-version").write_text("3.11.16\n", encoding="utf-8")
        errors = environment_policy_errors(self.root)
        self.assertTrue(any("Python version differs" in error for error in errors))

    def test_system_interpreter_cannot_create_run_records(self):
        result = subprocess.run(
            [sys._base_executable, "-m", "flbench", "new-run", "--owner", "zzr",
             "--method", "test-wrong-environment", "--config", "agents/zzr/configs/search.json"],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Environment is not aligned", result.stderr)
        self.assertFalse((self.root / "artifacts").exists())

    def test_dependency_lock_is_part_of_the_protocol_fingerprint(self):
        before = protocol_hash(self.root)
        lock = self.root / "uv.lock"
        lock.write_text(lock.read_text(encoding="utf-8") + "\n# test-only lock revision\n", encoding="utf-8")
        self.assertNotEqual(protocol_hash(self.root), before)

    def test_protocol_tracks_shared_code_but_not_personal_research_or_line_endings(self):
        before = protocol_hash(self.root)
        (self.root / "agents/zzr/RESEARCH.md").write_text("personal note", encoding="utf-8")
        self.assertEqual(protocol_hash(self.root), before)
        protocol = self.root / "PROTOCOL.md"
        protocol.write_bytes(protocol.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertEqual(protocol_hash(self.root), before)
        path = self.root / "benchmark/trainer.py"
        path.write_text(path.read_text(encoding="utf-8") + "\n# Shared behavior change\n", encoding="utf-8")
        self.assertNotEqual(protocol_hash(self.root), before)

    def test_published_summary_cannot_overwrite_existing_run(self):
        record = measured_fixture()
        path = publish_record(self.root, record)
        original = path.read_bytes()
        record.update(j_dev=0.99, mean_client_macro_f1=0.99)
        with self.assertRaises(ValueError):
            publish_record(self.root, record)
        self.assertEqual(path.read_bytes(), original)

    def test_bad_record_blocks_view_updates_without_skipping_failure(self):
        board = self.root / "shared/LEADERBOARD.md"
        before = board.read_bytes()
        (self.root / "agents/zzr/runs/truncated.json").write_text('{"run_id":', encoding="utf-8")
        with self.assertRaises(ValueError):
            synchronize(self.root)
        self.assertEqual(board.read_bytes(), before)

    def test_end_to_end_draft_failed_publish_and_consistent_views(self):
        for command in (["git", "init", "-q"], ["git", "add", "."],
                        ["git", "-c", "user.name=Scaffold Test", "-c", "user.email=test@example.invalid",
                         "commit", "-qm", "temporary test fixture"]):
            subprocess.run(command, cwd=self.root, check=True, capture_output=True)
        args = argparse.Namespace(owner="zzr", method="test-failure", config="agents/zzr/configs/search.json",
                                  hypothesis="H001", parent_method=None, seed=11)
        draft_path = new_record(self.root, args)
        record = load_json(draft_path)
        self.assertIsNone(record["mean_client_macro_f1"])
        self.assertEqual(record["status"], "planned")
        with self.assertRaises(ValueError):
            publish_record(self.root, record)
        record.update(status="failed", error="synthetic test: no training executed")
        draft_path.write_text(json.dumps(record), encoding="utf-8")
        result = self.cli("publish-run", str(draft_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.cli("publish-run", str(draft_path)).returncode, 0)
        self.assertNotEqual(self.cli("sync-leaderboard", "--check").returncode, 0)
        self.assertEqual(self.cli("sync-leaderboard").returncode, 0)
        result = self.cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.cli("sync-leaderboard", "--check").returncode, 0)
        index = (self.root / "shared/EXPERIMENT_INDEX.jsonl").read_text(encoding="utf-8")
        self.assertEqual(json.loads(index)["status"], "failed")
        self.assertNotIn("test-failure", (self.root / "shared/LEADERBOARD.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
