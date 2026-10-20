"""Synchronous CPU FedAvg/FedProx prototype with budgets and complete checkpoints."""

import copy
import random
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import torch

from benchmark.accounting import decode_message, encode_message, measure_round_cost
from benchmark.data import canonical_hash
from benchmark.evaluator import evaluate
from benchmark.interfaces import BudgetState, ClientHistory, ClientInfo, RoundFeedback
from benchmark.model import build_model
from benchmark.trainer import aggregate_equal, train_local
from flbench.environment import configure_cpu_runtime
from flbench.repository import protocol_hash


def client_metadata(config, dataset, seed):
    ids = sorted(dataset.train)
    if dataset.scenario.endswith("heterogeneous"):
        shuffled = ids.copy()
        random.Random(seed + 10000).shuffle(shuffled)
        tiers = config["system"]["heterogeneous_time_multipliers"]
        multipliers = {client: tiers[index * len(tiers) // len(ids)] for index, client in enumerate(shuffled)}
    else:
        multipliers = {client: config["system"]["homogeneous_time_multiplier"] for client in ids}
    return [ClientInfo(client, len(dataset.train[client][1]), multipliers[client]) for client in ids]


def profile_diagnostic_costs(config, dataset, seed):
    """Short measured costs for engineering validation; not a frozen research cost table."""
    model = build_model(config)
    generator = torch.Generator().manual_seed(seed + 99999)
    first = dataset.train[min(dataset.train)]
    train_local(model, first, generator, config)  # Warm up the optimizer/runtime.
    measurements = train_local(model, first, generator, config)["step_seconds"]
    state = {key: value.clone() for key, value in model.state_dict().items()}
    server_samples = []
    for _ in range(5):
        started = time.perf_counter()
        random.Random(seed).sample(list(dataset.train), config["training"]["clients_per_round"])
        payload = encode_message(state, {"client_id": 1, "round": 1, "role": "download"})
        decode_message(payload)
        aggregate_equal([state] * config["training"]["clients_per_round"])
        server_samples.append(time.perf_counter() - started)
    return {"reference_train_step_seconds": float(np.median(measurements)),
            "server_round_seconds": float(np.median(server_samples)),
            "step_measurements_seconds": measurements, "server_measurements_seconds": server_samples}


def _numpy_state():
    algorithm, keys, position, gaussian, cached = np.random.get_state()
    return {"algorithm": algorithm, "keys": keys.tolist(), "position": position,
            "has_gaussian": gaussian, "cached_gaussian": cached}


def run_experiment(root: Path, config, dataset, policy, cost_model, *, seed=11,
                   max_rounds=8, budget_seconds=10.0, proximal_mu=0.0,
                   checkpoint_path: Path | None = None, resume_from: Path | None = None):
    if type(max_rounds) is not int or max_rounds < 0 or budget_seconds <= 0:
        raise ValueError("Invalid round cap or diagnostic time budget.")
    if config["training"]["aggregation"] != "equal_client_weight":
        raise ValueError("This runner implements equal-client aggregation only.")
    configure_cpu_runtime(root, seed)
    infos = client_metadata(config, dataset, seed)
    by_id = {client.client_id: client for client in infos}
    count = config["training"]["clients_per_round"]
    if count > len(infos) or not count:
        raise ValueError("Invalid clients-per-round setting.")
    identity = {"protocol_hash": protocol_hash(root), "data_hash": dataset.manifest["content_sha256"],
                "training_config_hash": canonical_hash(config),
                "scenario": dataset.scenario, "seed": seed, "budget_seconds": budget_seconds,
                "proximal_mu": proximal_mu, "cost_model": cost_model,
                "policy_class": f"{type(policy).__module__}.{type(policy).__qualname__}"}
    identity_hash = canonical_hash(identity)
    model = build_model(config)
    histories = {client.client_id: ClientHistory() for client in infos}
    generators = {client.client_id: torch.Generator().manual_seed(seed * 1000 + client.client_id)
                  for client in infos}
    warmup = sorted(by_id)
    random.Random(seed + 20000).shuffle(warmup)
    completed, sim_seconds, up_bytes, down_bytes, training_steps = 0, 0.0, 0, 0, 0
    logs = []
    initial_metrics = None
    if resume_from is not None:
        saved = torch.load(resume_from, map_location="cpu", weights_only=True)
        if saved["format_version"] != 1 or saved["identity_hash"] != identity_hash:
            raise ValueError("Checkpoint protocol/data/config/policy/cost identity does not match.")
        model.load_state_dict(saved["model"])
        policy.load_state_dict(saved["policy"])
        for client in generators:
            generators[client].set_state(saved["client_rng"][client])
        histories = {client: ClientHistory(**value) for client, value in saved["histories"].items()}
        completed, sim_seconds = saved["completed_rounds"], saved["sim_seconds_used"]
        up_bytes, down_bytes, training_steps = saved["up_bytes"], saved["down_bytes"], saved["training_steps"]
        logs, initial_metrics = saved["logs"], saved["initial_metrics"]
        random.setstate(saved["python_rng"])
        np_state = saved["numpy_rng"]
        np.random.set_state((np_state["algorithm"], np.asarray(np_state["keys"], dtype=np.uint32),
                             np_state["position"], np_state["has_gaussian"], np_state["cached_gaussian"]))
        torch.set_rng_state(saved["torch_rng"])
    if initial_metrics is None:
        initial_metrics = evaluate(model, dataset)
    wall_started = time.perf_counter()
    stop_reason = "round_cap"
    while completed < max_rounds:
        policy_before = copy.deepcopy(policy.state_dict())
        if completed < config["training"]["warmup_rounds"]:
            offset = completed * count % len(warmup)
            selected = [warmup[(offset + index) % len(warmup)] for index in range(count)]
        else:
            selected = policy.select(infos, BudgetState(sim_seconds, budget_seconds), histories, count)
        if (len(selected) != count or len(set(selected)) != count
                or any(type(client) is not int or client not in by_id for client in selected)):
            raise ValueError("Selector returned invalid, duplicate or unavailable clients.")
        ordered = sorted(selected)
        state = {key: value.detach().clone() for key, value in model.state_dict().items()}
        downloads, message_sizes = {}, {}
        for client in ordered:
            downloads[client] = encode_message(state, {"client_id": client, "round": completed + 1,
                                                       "role": "download"})
            preview = encode_message(state, {"client_id": client, "round": completed + 1,
                                              "role": "upload", "loss": 0.0,
                                              "steps": config["training"]["local_steps"]})
            message_sizes[client] = (len(downloads[client]), len(preview))
        cost = measure_round_cost(config, [by_id[client] for client in ordered], message_sizes, cost_model)
        if sim_seconds + cost["sim_seconds"] > budget_seconds:
            policy.load_state_dict(policy_before)
            stop_reason = "simulated_budget"
            break  # No local training or partial aggregation occurs beyond the budget.
        updates, losses = [], {}
        for client in ordered:
            local_model = copy.deepcopy(model)
            local_model.load_state_dict(decode_message(downloads[client])["state_dict"])
            feedback = train_local(local_model, dataset.train[client], generators[client], config,
                                   proximal_mu=proximal_mu)
            update = encode_message(dict(local_model.state_dict()),
                                    {"client_id": client, "round": completed + 1, "role": "upload",
                                     "loss": feedback["loss"], "steps": feedback["steps"]})
            if len(update) != message_sizes[client][1]:
                raise ValueError("Actual upload size differs from budget preflight.")
            updates.append(decode_message(update)["state_dict"])
            losses[client] = feedback["loss"]
        model.load_state_dict(aggregate_equal(updates))
        sim_seconds += cost["sim_seconds"]
        completed += 1
        up_bytes += cost["up_bytes"]
        down_bytes += cost["down_bytes"]
        training_steps += cost["training_steps"]
        for client in ordered:
            histories[client] = replace(histories[client], participations=histories[client].participations + 1,
                                         last_participation_sim_seconds=sim_seconds,
                                         last_observed_train_loss=losses[client])
        policy.observe(RoundFeedback(tuple(selected), sim_seconds, losses))
        logs.append({"round": completed, "selected_clients": selected, "sim_seconds_used": sim_seconds,
                     "up_bytes": up_bytes, "down_bytes": down_bytes, "training_steps": training_steps,
                     "mean_local_loss": sum(losses.values()) / len(losses),
                     "synchronization_wait_seconds": cost["synchronization_wait_seconds"]})
    metrics = evaluate(model, dataset)
    saved = {"format_version": 1, "identity": identity, "identity_hash": identity_hash,
             "model": {key: value.detach().clone() for key, value in model.state_dict().items()},
             "policy": policy.state_dict(), "client_rng": {client: gen.get_state() for client, gen in generators.items()},
             "histories": {client: asdict(history) for client, history in histories.items()},
             "completed_rounds": completed, "sim_seconds_used": sim_seconds,
             "up_bytes": up_bytes, "down_bytes": down_bytes, "training_steps": training_steps,
             "logs": logs, "initial_metrics": initial_metrics,
             "torch_rng": torch.get_rng_state(), "python_rng": random.getstate(), "numpy_rng": _numpy_state()}
    if checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(saved, checkpoint_path)
    return {"state": saved, "summary": {"purpose": "short_federated_pipeline_validation",
              "method": "fedprox_u" if proximal_mu else "fedavg_u", "scenario": dataset.scenario,
              "completed_rounds": completed, "stop_reason": stop_reason, "sim_seconds_used": sim_seconds,
              "budget_sim_seconds": budget_seconds, "up_bytes": up_bytes, "down_bytes": down_bytes,
              "training_steps": training_steps, "wall_seconds": time.perf_counter() - wall_started,
              "initial_mean_client_macro_f1": initial_metrics["mean_client_macro_f1"],
              "mean_client_macro_f1": metrics["mean_client_macro_f1"],
              "evaluation_scope": metrics["scope"], "validation_clients": metrics["num_clients"],
              "per_client_metrics": metrics["clients"]}}
