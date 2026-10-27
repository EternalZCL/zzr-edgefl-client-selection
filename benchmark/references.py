"""Exposure-matched explanatory references; not fixed-time FL competitors."""

import copy
import time

from benchmark.evaluator import evaluate
from benchmark.model import build_model
from benchmark.trainer import train_local
from flbench.environment import configure_cpu_runtime


def run_reference(root, config, dataset, kind, *, seed, equivalent_rounds=200):
    import torch

    if kind not in {"local_only", "centralized"}:
        raise ValueError("Unknown explanatory reference.")
    configure_cpu_runtime(root, seed)
    initial = build_model(config)
    started, cpu_started = time.perf_counter(), time.process_time()
    total_steps = equivalent_rounds * config["training"]["clients_per_round"] * config["training"]["local_steps"]
    current = copy.deepcopy(config)
    if kind == "centralized":
        model = initial
        x = torch.cat([data[0] for data in dataset.train.values()])
        y = torch.cat([data[1] for data in dataset.train.values()])
        current["training"]["local_steps"] = total_steps
        train_local(model, (x, y), torch.Generator().manual_seed(seed * 1000), current)
        actual_steps, completed = total_steps, total_steps
        state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    else:
        steps, remainder = divmod(total_steps, len(dataset.train))
        if remainder:
            raise ValueError("Reference exposure must divide equally among clients.")
        models = {}
        for client, data in sorted(dataset.train.items()):
            models[client] = copy.deepcopy(initial)
            current["training"]["local_steps"] = steps
            train_local(models[client], data, torch.Generator().manual_seed(seed * 1000 + client), current)
        model, actual_steps, completed = models, steps * len(models), steps
        state = {client: {k: v.detach().clone() for k, v in m.state_dict().items()} for client, m in models.items()}
    metrics = evaluate(model, dataset)
    return {"state": {"model": state, "logs": []}, "summary": {
        "purpose": "exposure_matched_reference_not_fixed_time_competitor", "method": kind,
        "scenario": dataset.scenario, "completed_rounds": completed, "stop_reason": "fixed_exposure",
        "sim_seconds_used": 0.0, "up_bytes": 0, "down_bytes": 0,
        "training_steps": actual_steps, "wall_seconds": time.perf_counter() - started,
        "cpu_seconds": time.process_time() - cpu_started,
        "mean_client_macro_f1": metrics["mean_client_macro_f1"],
        "evaluation_scope": metrics["scope"], "validation_clients": metrics["num_clients"],
        "per_client_metrics": metrics["clients"], "tail_20_percent_macro_f1": metrics["tail_20_percent_macro_f1"],
        "pooled_macro_f1": metrics["pooled_macro_f1"], "curve": [],
        "reference_equivalent_federated_rounds": equivalent_rounds,
        "note": "No FL simulated cost claimed; zero communication denotes unmodeled reference links."}}
