"""Analytic SCAFFOLD, selection, budget and full-state recovery checks."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import test_pipeline
ROOT = test_pipeline.ROOT
from baselines.scheduling import RoundRobinPolicy, FastRandomPolicy, OortPolicy
from baselines.uniform import UniformPolicy
from benchmark.interfaces import BudgetState, ClientHistory, ClientInfo, RoundFeedback
from benchmark.simulator import run_experiment, scaffold_controls
from benchmark.trainer import aggregate_equal, train_local
from benchmark.model import build_model
from flbench.environment import configure_cpu_runtime

import torch


def candidate(seed=11, **kwargs):
    spec = importlib.util.spec_from_file_location("edgefl_agent_ghj", ROOT / "agents/ghj/policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Policy(seed=seed, **kwargs)


class ResearchCorrectnessTests(unittest.TestCase):
    def setUp(self):
        fixture = test_pipeline.PipelineTests()
        fixture.setUp()
        self.config, self.dataset, self.costs = fixture.config, fixture.dataset, fixture.costs

    def test_control_variates_correct_gradient_and_option_two(self):
        configure_cpu_runtime(ROOT, 11)
        self.config["training"]["local_steps"] = 1
        model = build_model(self.config)
        expected = copy.deepcopy(model)
        old = {k: v.clone() for k, v in model.state_dict().items()}
        server = {k: torch.full_like(v, 0.2) for k, v in old.items()}
        local = {k: torch.full_like(v, 0.1) for k, v in old.items()}
        rng = torch.Generator().manual_seed(5)
        ids = torch.randint(24, (self.config["training"]["batch_size"],), generator=rng)
        x, y = self.dataset.train[1]
        torch.nn.functional.cross_entropy(expected(x[ids]), y[ids]).backward()
        lr = self.config["training"]["initial_learning_rate"]
        with torch.no_grad():
            for p in expected.parameters():
                p.add_(-lr * (p.grad + 0.1))
        train_local(model, self.dataset.train[1], torch.Generator().manual_seed(5), self.config,
                    server_control=server, client_control=local)
        for k, v in model.state_dict().items():
            torch.testing.assert_close(v, expected.state_dict()[k], atol=1e-7, rtol=1e-6)
        updated, delta = scaffold_controls(old, model.state_dict(), server, local, 1, lr)
        for k in old:
            torch.testing.assert_close(delta[k], updated[k] - local[k])
            torch.testing.assert_close(updated[k], -0.1 + (old[k] - model.state_dict()[k]) / lr)

    def test_scaffold_global_control_equals_population_mean_and_messages_are_paid(self):
        ordinary = run_experiment(ROOT, self.config, self.dataset, UniformPolicy(11), self.costs, max_rounds=4)
        result = run_experiment(ROOT, self.config, self.dataset, UniformPolicy(11), self.costs,
                                max_rounds=4, scaffold=True)
        controls = result["state"]["client_controls"]
        mean = aggregate_equal(list(controls.values()))
        for k in mean:
            torch.testing.assert_close(mean[k], result["state"]["server_control"][k], atol=1e-6, rtol=1e-5)
        self.assertGreater(result["summary"]["up_bytes"], ordinary["summary"]["up_bytes"])
        self.assertGreater(result["summary"]["down_bytes"], ordinary["summary"]["down_bytes"])
        self.assertGreater(result["summary"]["sim_seconds_used"], ordinary["summary"]["sim_seconds_used"])

    def test_all_selectors_resume_exactly_including_scaffold_controls(self):
        for factory, scaffold in [(RoundRobinPolicy, False), (FastRandomPolicy, False),
                                   (OortPolicy, False), (candidate, False), (UniformPolicy, True)]:
            with self.subTest(factory=factory), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "checkpoint.pt"
                full = run_experiment(ROOT, self.config, self.dataset, factory(11), self.costs,
                                      max_rounds=8, scaffold=scaffold)
                run_experiment(ROOT, self.config, self.dataset, factory(11), self.costs,
                               max_rounds=3, scaffold=scaffold, checkpoint_path=path)
                resumed = run_experiment(ROOT, self.config, self.dataset, factory(11), self.costs,
                                         max_rounds=8, scaffold=scaffold, resume_from=path)
                self.assertEqual(full["state"]["logs"], resumed["state"]["logs"])
                self.assertEqual(full["state"]["policy"], resumed["state"]["policy"])
                for k, value in full["state"]["model"].items():
                    self.assertTrue(torch.equal(value, resumed["state"]["model"][k]))
                for k, value in full["state"]["server_control"].items():
                    self.assertTrue(torch.equal(value, resumed["state"]["server_control"][k]))

    def test_weighted_fedavg_matches_analytic_average(self):
        actual = aggregate_equal([{"w": torch.tensor([1.0])}, {"w": torch.tensor([5.0])}], [1, 3])
        self.assertEqual(actual["w"].item(), 4.0)

    def test_rr_cycle_and_zero_exploration_fastest(self):
        clients = [ClientInfo(i, 20, 1 if i < 10 else 16) for i in range(30)]
        rr = RoundRobinPolicy(11)
        budget = BudgetState(1, 10)
        sequence = [i for _ in range(5) for i in rr.select(clients, budget, {}, 6)]
        self.assertEqual(set(sequence), set(range(30)))
        fast = FastRandomPolicy(11, exploration=0)
        self.assertTrue(all(i < 10 for i in fast.select(clients, budget, {}, 6)))

    def test_coverage_uses_stale_client_and_no_wait_matches_speed_tier(self):
        clients = [ClientInfo(i, 20, 1 if i < 10 else 16) for i in range(30)]
        history = {i: ClientHistory(1, 9.9 if i != 29 else 0.1, 1.0) for i in range(30)}
        budget = BudgetState(10, 20)
        self.assertIn(29, candidate(11).select(clients, budget, history, 6))
        selected = candidate(11, ablation="no_wait").select(clients, budget, history, 6)
        self.assertTrue(any(i >= 10 for i in selected))
        for policy in (RoundRobinPolicy(11), FastRandomPolicy(11), OortPolicy(11), candidate(11)):
            policy.select(clients, budget, history, 6)
            state = json.loads(json.dumps(policy.state_dict()))
            policy.load_state_dict(state)
            self.assertEqual(len(set(policy.select(clients, budget, history, 6))), 6)

    def test_budget_full_run_stops_without_extra_steps(self):
        result = run_experiment(ROOT, self.config, self.dataset, OortPolicy(11), self.costs,
                                max_rounds=None, budget_seconds=0.25, capture_curve=True)
        summary = result["summary"]
        self.assertEqual(summary["stop_reason"], "simulated_budget")
        self.assertLessEqual(summary["sim_seconds_used"], 0.25)
        self.assertEqual(summary["training_steps"], summary["completed_rounds"] * 4)
        self.assertEqual(len(summary["curve"]), 4)
        self.assertTrue(all(point["sim_seconds_used"] <= point["time_point"] for point in summary["curve"]))


if __name__ == "__main__":
    unittest.main()
