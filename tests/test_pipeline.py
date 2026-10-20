"""Small mathematical/integration checks; no network or real HAPT cache required."""

import copy
import tempfile
import unittest
from pathlib import Path

from flbench.environment import configure_cpu_runtime
from flbench.repository import CONFIG, COST, load_json

ROOT = Path(__file__).resolve().parents[1]
configure_cpu_runtime(ROOT, 11)

import numpy as np
import torch
from baselines.uniform import UniformPolicy
from benchmark.accounting import decode_message, encode_message, measure_round_cost
from benchmark.data import PreparedData, audit_intervals, load_prepared, redistribute_near_iid, window_features
from benchmark.evaluator import evaluate
from benchmark.model import build_model
from benchmark.simulator import client_metadata, run_experiment
from benchmark.trainer import aggregate_equal, train_local


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = load_json(ROOT / CONFIG)
        self.config["training"].update(clients_per_round=1, warmup_rounds=1)
        generator = torch.Generator().manual_seed(1234)
        self.dataset = PreparedData(
            train={client: (torch.randn(24, 48, generator=generator), torch.arange(24) % 6)
                   for client in (1, 2)},
            validation={client: (torch.randn(12, 48, generator=generator), torch.arange(12) % 6)
                        for client in (1, 2)},
            manifest={"content_sha256": "a" * 64,
                      "split_contract": {"search_validation_clients": [1, 2]}},
            scenario="natural_heterogeneous")
        self.costs = load_json(ROOT / COST)
        self.costs.update(reference_train_step_seconds=0.001, server_round_seconds=0.0001)

    def test_feature_definition_on_constant_channels(self):
        windows = np.tile(np.arange(1, 7, dtype=float), (1, 128, 1))
        result = window_features(windows).reshape(6, 8)
        for channel, value in enumerate(range(1, 7)):
            np.testing.assert_allclose(result[channel], [value, 0, value, value, value, 0, 0, value])

    def test_raw_overlap_detection_across_train_and_validation(self):
        adjacent = [{"client": 1, "experiment": 1, "split": "train", "start": 0, "stop": 128},
                    {"client": 1, "experiment": 1, "split": "validation", "start": 128, "stop": 256}]
        audit_intervals(adjacent)
        adjacent[1]["start"] = 127
        with self.assertRaises(ValueError):
            audit_intervals(adjacent)

    def test_near_iid_preserves_every_sample_and_client_size(self):
        train = {1: (torch.arange(96, dtype=torch.float32).reshape(2, 48), torch.tensor([0, 0])),
                 2: (torch.arange(96, 384, dtype=torch.float32).reshape(6, 48), torch.tensor([1, 1, 1, 2, 2, 2]))}
        redistributed = redistribute_near_iid(train, 11)
        self.assertEqual([len(redistributed[client][1]) for client in train], [2, 6])
        before = sorted(tuple(row.tolist()) for x, _ in train.values() for row in x)
        after = sorted(tuple(row.tolist()) for x, _ in redistributed.values() for row in x)
        self.assertEqual(before, after)
        self.assertTrue(torch.equal(torch.bincount(torch.cat([v[1] for v in train.values()]), minlength=6),
                                    torch.bincount(torch.cat([v[1] for v in redistributed.values()]), minlength=6)))

    def test_equal_client_aggregation_and_message_roundtrip(self):
        state = aggregate_equal([{"weight": torch.tensor([1.0, 3.0])},
                                 {"weight": torch.tensor([3.0, 5.0])}])
        self.assertTrue(torch.equal(state["weight"], torch.tensor([2.0, 4.0])))
        payload = encode_message(state, {"loss": 0.0})
        actual = encode_message(state, {"loss": 0.123456})
        self.assertEqual(len(payload), len(actual))
        self.assertTrue(torch.equal(decode_message(actual)["state_dict"]["weight"], state["weight"]))

    def test_single_client_local_update_matches_plain_sgd(self):
        configure_cpu_runtime(ROOT, 11)
        model = build_model(self.config)
        manual = copy.deepcopy(model)
        short = copy.deepcopy(self.config)
        short["training"]["local_steps"] = 1
        generator = torch.Generator().manual_seed(5)
        ids = torch.randint(24, (short["training"]["batch_size"],), generator=generator)
        x, y = self.dataset.train[1]
        optimizer = torch.optim.SGD(manual.parameters(), lr=short["training"]["initial_learning_rate"])
        optimizer.zero_grad(set_to_none=True)
        torch.nn.functional.cross_entropy(manual(x[ids]), y[ids]).backward()
        optimizer.step()
        train_local(model, (x, y), torch.Generator().manual_seed(5), short)
        self.assertTrue(all(torch.equal(value, manual.state_dict()[key]) for key, value in model.state_dict().items()))

    def test_zero_mu_fedprox_reduces_to_fedavg(self):
        configure_cpu_runtime(ROOT, 11)
        model = build_model(self.config)
        alternate = copy.deepcopy(model)
        train_local(model, self.dataset.train[1], torch.Generator().manual_seed(5), self.config)
        train_local(alternate, self.dataset.train[1], torch.Generator().manual_seed(5), self.config, proximal_mu=0)
        self.assertTrue(all(torch.equal(value, alternate.state_dict()[key]) for key, value in model.state_dict().items()))

    def test_budget_rejection_preserves_weights_and_policy_rng(self):
        baseline = run_experiment(ROOT, self.config, self.dataset, UniformPolicy(11), self.costs,
                                  max_rounds=0, budget_seconds=1e-12)
        policy = UniformPolicy(11)
        before = copy.deepcopy(policy.state_dict())
        self.config["training"]["warmup_rounds"] = 0  # Exercise selector rollback, not just warmup.
        stopped = run_experiment(ROOT, self.config, self.dataset, policy, self.costs,
                                 max_rounds=2, budget_seconds=1e-12)
        self.assertEqual(stopped["summary"]["training_steps"], 0)
        self.assertEqual(stopped["summary"]["up_bytes"], 0)
        self.assertEqual(policy.state_dict(), before)
        self.assertTrue(all(torch.equal(value, stopped["state"]["model"][key])
                            for key, value in baseline["state"]["model"].items()))

    def test_checkpoint_matches_continuous_and_rejects_changed_training(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "checkpoint.pt"
            full = run_experiment(ROOT, self.config, self.dataset, UniformPolicy(11), self.costs, max_rounds=4)
            run_experiment(ROOT, self.config, self.dataset, UniformPolicy(11), self.costs,
                           max_rounds=2, checkpoint_path=path)
            resumed = run_experiment(ROOT, self.config, self.dataset, UniformPolicy(11), self.costs,
                                     max_rounds=4, resume_from=path)
            self.assertEqual(full["state"]["logs"], resumed["state"]["logs"])
            self.assertTrue(all(torch.equal(value, resumed["state"]["model"][key])
                                for key, value in full["state"]["model"].items()))
            changed = copy.deepcopy(self.config)
            changed["training"]["local_steps"] += 1
            with self.assertRaises(ValueError):
                run_experiment(ROOT, changed, self.dataset, UniformPolicy(11), self.costs,
                               max_rounds=4, resume_from=path)

    def test_reserved_labels_and_wrong_client_set_are_rejected(self):
        with self.assertRaises(ValueError):
            load_prepared(ROOT, scenario="natural_heterogeneous", evaluation_stage="test")
        self.dataset.validation[3] = self.dataset.validation[1]
        with self.assertRaises(ValueError):
            evaluate(build_model(self.config), self.dataset)

    def test_speed_tiers_and_network_bytes_match_the_declared_system(self):
        many = copy.copy(self.dataset)
        many.train = {client: self.dataset.train[1] for client in range(1, 31)}
        infos = client_metadata(self.config, many, 11)
        self.assertEqual(sorted(info.compute_time_multiplier for info in infos), [1] * 10 + [4] * 10 + [16] * 10)
        many.scenario = "natural_homogeneous"
        homogeneous = client_metadata(self.config, many, 11)
        self.assertAlmostEqual(sum(1 / info.compute_time_multiplier for info in infos),
                               sum(1 / info.compute_time_multiplier for info in homogeneous))
        messages = {info.client_id: (100, 200) for info in infos[:2]}
        cost = measure_round_cost(self.config, infos[:2], messages, self.costs)
        self.assertEqual((cost["down_bytes"], cost["up_bytes"]), (200, 400))


if __name__ == "__main__":
    unittest.main()
