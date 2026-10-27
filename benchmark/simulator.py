"""Budgeted synchronous FL, including SCAFFOLD and resumable complete state."""

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
        multipliers = {c: tiers[i * len(tiers) // len(ids)] for i, c in enumerate(shuffled)}
    else:
        multipliers = {c: config["system"]["homogeneous_time_multiplier"] for c in ids}
    return [ClientInfo(c, len(dataset.train[c][1]), multipliers[c]) for c in ids]


def profile_diagnostic_costs(config, dataset, seed):
    """Short engineering snapshot; research profiling uses the campaign profiler."""
    model = build_model(config)
    generator = torch.Generator().manual_seed(seed + 99999)
    first = dataset.train[min(dataset.train)]
    train_local(model, first, generator, config)
    measurements = train_local(model, first, generator, config)["step_seconds"]
    state = {k: v.clone() for k, v in model.state_dict().items()}
    samples = []
    for _ in range(5):
        started = time.perf_counter()
        payload = encode_message(state, {"client_id": 1, "round": 1, "role": "download"})
        decode_message(payload)
        aggregate_equal([state] * config["training"]["clients_per_round"])
        samples.append(time.perf_counter() - started)
    return {"reference_train_step_seconds": float(np.median(measurements)),
            "server_round_seconds": float(np.median(samples)),
            "step_measurements_seconds": measurements, "server_measurements_seconds": samples}


def _numpy_state():
    algorithm, keys, position, gaussian, cached = np.random.get_state()
    return {"algorithm": algorithm, "keys": keys.tolist(), "position": position,
            "has_gaussian": gaussian, "cached_gaussian": cached}


def scaffold_controls(old_state, new_state, server_control, client_control, steps, learning_rate):
    """SCAFFOLD option II; global control is the population mean of client controls."""
    updated = {k: client_control[k] - server_control[k]
               + (old_state[k] - new_state[k]) / (steps * learning_rate) for k in old_state}
    delta = {k: updated[k] - client_control[k] for k in updated}
    return updated, delta


def run_experiment(root: Path, config, dataset, policy, cost_model, *, seed=11,
                   max_rounds=8, budget_seconds=10.0, proximal_mu=0.0, scaffold=False,
                   server_learning_rate=1.0, sample_weighted=False, capture_curve=False,
                   checkpoint_path: Path | None = None, resume_from: Path | None = None):
    if ((max_rounds is not None and (type(max_rounds) is not int or max_rounds < 0))
            or not np.isfinite(budget_seconds) or budget_seconds <= 0):
        raise ValueError("Invalid round cap or simulated time budget.")
    if scaffold and (proximal_mu or sample_weighted):
        raise ValueError("SCAFFOLD uses equal client aggregation and no proximal term.")
    if config["training"]["aggregation"] != "equal_client_weight":
        raise ValueError("Shared training must use equal-client aggregation.")
    configure_cpu_runtime(root, seed)
    infos = client_metadata(config, dataset, seed)
    by_id = {c.client_id: c for c in infos}
    count = config["training"]["clients_per_round"]
    if count > len(infos) or not count:
        raise ValueError("Invalid clients-per-round setting.")
    identity = {"protocol_hash": protocol_hash(root), "data_hash": dataset.manifest["content_sha256"],
                "training_config_hash": canonical_hash(config), "scenario": dataset.scenario,
                "evaluation_stage": getattr(dataset, "evaluation_stage", "development"),
                "seed": seed, "budget_seconds": budget_seconds, "proximal_mu": proximal_mu,
                "scaffold": scaffold, "server_learning_rate": server_learning_rate,
                "sample_weighted": sample_weighted, "capture_curve": capture_curve,
                "cost_model": cost_model, "initial_policy_state": policy.state_dict(),
                "policy_class": f"{type(policy).__module__}.{type(policy).__qualname__}"}
    identity_hash = canonical_hash(identity)
    model = build_model(config)
    histories = {c.client_id: ClientHistory() for c in infos}
    generators = {c.client_id: torch.Generator().manual_seed(seed * 1000 + c.client_id) for c in infos}
    zeros = {k: torch.zeros_like(v) for k, v in model.state_dict().items()}
    server_control = copy.deepcopy(zeros)
    client_controls = {c.client_id: copy.deepcopy(zeros) for c in infos} if scaffold else {}
    warmup = sorted(by_id)
    random.Random(seed + 20000).shuffle(warmup)
    completed, sim_seconds, up_bytes, down_bytes, training_steps = 0, 0.0, 0, 0, 0
    logs, curve = [], []
    initial_metrics = None
    cumulative_wall, cumulative_cpu = 0.0, 0.0
    longest_wait = {c.client_id: 0.0 for c in infos}
    if resume_from is not None:
        saved = torch.load(resume_from, map_location="cpu", weights_only=True)
        if saved["format_version"] != 2 or saved["identity_hash"] != identity_hash:
            raise ValueError("Checkpoint protocol/data/config/policy/cost identity does not match.")
        model.load_state_dict(saved["model"])
        policy.load_state_dict(saved["policy"])
        for client in generators:
            generators[client].set_state(saved["client_rng"][client])
        histories = {c: ClientHistory(**v) for c, v in saved["histories"].items()}
        completed, sim_seconds = saved["completed_rounds"], saved["sim_seconds_used"]
        up_bytes, down_bytes, training_steps = saved["up_bytes"], saved["down_bytes"], saved["training_steps"]
        logs, curve, initial_metrics = saved["logs"], saved["curve"], saved["initial_metrics"]
        server_control, client_controls = saved["server_control"], saved["client_controls"]
        longest_wait = saved["longest_wait"]
        cumulative_wall, cumulative_cpu = saved["wall_seconds"], saved["cpu_seconds"]
        random.setstate(saved["python_rng"])
        n = saved["numpy_rng"]
        np.random.set_state((n["algorithm"], np.asarray(n["keys"], dtype=np.uint32),
                             n["position"], n["has_gaussian"], n["cached_gaussian"]))
        torch.set_rng_state(saved["torch_rng"])
    if initial_metrics is None:
        initial_metrics = evaluate(model, dataset)
    wall_started, cpu_started = time.perf_counter(), time.process_time()

    def snapshot():
        return {"format_version": 2, "identity": identity, "identity_hash": identity_hash,
                "model": {k: v.detach().clone() for k, v in model.state_dict().items()},
                "policy": copy.deepcopy(policy.state_dict()),
                "client_rng": {c: gen.get_state() for c, gen in generators.items()},
                "histories": {c: asdict(h) for c, h in histories.items()},
                "completed_rounds": completed, "sim_seconds_used": sim_seconds,
                "up_bytes": up_bytes, "down_bytes": down_bytes, "training_steps": training_steps,
                "logs": copy.deepcopy(logs), "curve": copy.deepcopy(curve), "initial_metrics": initial_metrics,
                "server_control": copy.deepcopy(server_control), "client_controls": copy.deepcopy(client_controls),
                "longest_wait": dict(longest_wait), "wall_seconds": cumulative_wall + time.perf_counter() - wall_started,
                "cpu_seconds": cumulative_cpu + time.process_time() - cpu_started,
                "torch_rng": torch.get_rng_state(), "python_rng": random.getstate(), "numpy_rng": _numpy_state()}

    def save():
        if checkpoint_path is not None:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = checkpoint_path.with_suffix(".tmp")
            torch.save(snapshot(), temporary)
            temporary.replace(checkpoint_path)

    stop_reason = "round_cap"
    while max_rounds is None or completed < max_rounds:
        policy_before = copy.deepcopy(policy.state_dict())
        if completed < config["training"]["warmup_rounds"]:
            offset = completed * count % len(warmup)
            selected = [warmup[(offset + i) % len(warmup)] for i in range(count)]
        else:
            selected = policy.select(infos, BudgetState(sim_seconds, budget_seconds), histories, count)
        if (len(selected) != count or len(set(selected)) != count
                or any(type(c) is not int or c not in by_id for c in selected)):
            raise ValueError("Selector returned invalid, duplicate or unavailable clients.")
        ordered = sorted(selected)
        state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        download_state = dict(state)
        if scaffold:
            download_state.update({"control::" + k: v for k, v in server_control.items()})
        downloads, message_sizes = {}, {}
        for client in ordered:
            metadata = {"client_id": client, "round": completed + 1, "role": "download"}
            downloads[client] = encode_message(download_state, metadata)
            metadata.update(role="upload", loss=0.0, loss_rms=0.0, steps=config["training"]["local_steps"])
            preview = encode_message(download_state, metadata)
            message_sizes[client] = (len(downloads[client]), len(preview))
        effective_cost = dict(cost_model)
        selector_key = getattr(policy, "cost_key", "uniform")
        extra = cost_model.get("selector_seconds", {}).get(selector_key, 0.0)
        if completed < config["training"]["warmup_rounds"]:
            extra = cost_model.get("selector_seconds", {}).get("uniform", 0.0)
        effective_cost["server_round_seconds"] += extra
        if scaffold:
            effective_cost["server_round_seconds"] += cost_model.get("scaffold_server_extra_seconds", 0.0)
            effective_cost["reference_train_step_seconds"] = cost_model.get(
                "scaffold_train_step_seconds", cost_model["reference_train_step_seconds"])
        cost = measure_round_cost(config, [by_id[c] for c in ordered], message_sizes, effective_cost)
        # Record last completed model at each preregistered time point; no score enters policy.
        if capture_curve:
            while len(curve) < 4 and (len(curve) + 1) * budget_seconds / 4 < sim_seconds + cost["sim_seconds"]:
                point = (len(curve) + 1) * budget_seconds / 4
                curve.append({"budget_fraction": (len(curve) + 1) / 4, "time_point": point,
                              "completed_rounds": completed, "sim_seconds_used": sim_seconds,
                              "metrics": evaluate(model, dataset)})
        if sim_seconds + cost["sim_seconds"] > budget_seconds:
            policy.load_state_dict(policy_before)
            stop_reason = "simulated_budget"
            break
        updates, deltas, losses, rms = [], [], {}, {}
        for client in ordered:
            local_model = copy.deepcopy(model)
            received = decode_message(downloads[client])["state_dict"]
            local_model.load_state_dict({k: received[k] for k in state})
            feedback = train_local(local_model, dataset.train[client], generators[client], config,
                                   proximal_mu=proximal_mu,
                                   server_control=server_control if scaffold else None,
                                   client_control=client_controls.get(client))
            local_state = dict(local_model.state_dict())
            upload_state = dict(local_state)
            if scaffold:
                updated, delta = scaffold_controls(state, local_state, server_control, client_controls[client],
                                                   config["training"]["local_steps"],
                                                   config["training"]["initial_learning_rate"])
                client_controls[client] = updated
                upload_state.update({"control::" + k: v for k, v in delta.items()})
            update = encode_message(upload_state, {"client_id": client, "round": completed + 1,
                                    "role": "upload", "loss": feedback["loss"], "loss_rms": feedback["loss_rms"],
                                    "steps": feedback["steps"]})
            if len(update) != message_sizes[client][1]:
                raise ValueError("Actual upload size differs from budget preflight.")
            decoded = decode_message(update)["state_dict"]
            updates.append({k: decoded[k] for k in state})
            if scaffold:
                deltas.append({k: decoded["control::" + k] for k in state})
            losses[client], rms[client] = feedback["loss"], feedback["loss_rms"]
        weights = [by_id[c].train_examples for c in ordered] if sample_weighted else None
        aggregate = aggregate_equal(updates, weights)
        if scaffold:
            aggregate = {k: state[k] + server_learning_rate * (v - state[k]) for k, v in aggregate.items()}
            mean_delta = aggregate_equal(deltas)
            server_control = {k: server_control[k] + count / len(infos) * mean_delta[k] for k in state}
        model.load_state_dict(aggregate)
        sim_seconds += cost["sim_seconds"]
        completed += 1
        up_bytes, down_bytes = up_bytes + cost["up_bytes"], down_bytes + cost["down_bytes"]
        training_steps += cost["training_steps"]
        for client in ordered:
            h = histories[client]
            longest_wait[client] = max(longest_wait[client], sim_seconds - (h.last_participation_sim_seconds or 0.0))
            histories[client] = replace(h, participations=h.participations + 1,
                last_participation_sim_seconds=sim_seconds, last_observed_train_loss=losses[client],
                last_observed_train_loss_rms=rms[client])
        policy.observe(RoundFeedback(tuple(selected), sim_seconds, losses, rms))
        logs.append({"round": completed, "selected_clients": selected, "sim_seconds_used": sim_seconds,
                     "up_bytes": up_bytes, "down_bytes": down_bytes, "training_steps": training_steps,
                     "mean_local_loss": sum(losses.values()) / len(losses), "selector_seconds": extra,
                     "synchronization_wait_seconds": cost["synchronization_wait_seconds"]})
        if completed % 50 == 0:
            save()
    metrics = evaluate(model, dataset)
    if capture_curve and stop_reason == "simulated_budget" and len(curve) < 4:
        curve.append({"budget_fraction": 1.0, "time_point": budget_seconds,
                      "completed_rounds": completed, "sim_seconds_used": sim_seconds, "metrics": metrics})
    for c, h in histories.items():
        longest_wait[c] = max(longest_wait[c], sim_seconds - (h.last_participation_sim_seconds or 0.0))
    saved = snapshot()
    save()
    return {"state": saved, "summary": {"purpose": "fixed_budget_research" if max_rounds is None else "short_federated_pipeline_validation",
        "method": "scaffold" if scaffold else ("fedprox_u" if proximal_mu else "fedavg_u"),
        "scenario": dataset.scenario, "completed_rounds": completed, "stop_reason": stop_reason,
        "sim_seconds_used": sim_seconds, "budget_sim_seconds": budget_seconds,
        "up_bytes": up_bytes, "down_bytes": down_bytes, "training_steps": training_steps,
        "wall_seconds": saved["wall_seconds"], "cpu_seconds": saved["cpu_seconds"],
        "initial_mean_client_macro_f1": initial_metrics["mean_client_macro_f1"],
        "mean_client_macro_f1": metrics["mean_client_macro_f1"], "evaluation_scope": metrics["scope"],
        "validation_clients": metrics["num_clients"], "per_client_metrics": metrics["clients"],
        "tail_20_percent_macro_f1": metrics["tail_20_percent_macro_f1"],
        "pooled_macro_f1": metrics["pooled_macro_f1"], "curve": curve,
        "participations": {c: h.participations for c, h in histories.items()}, "longest_wait_seconds": longest_wait,
        "speed_multipliers": {c.client_id: c.compute_time_multiplier for c in infos},
        "synchronization_wait_seconds": sum(row["synchronization_wait_seconds"] for row in logs)}}
