"""Actual serialized messages; fixed, checkpointed diagnostic time coefficients."""

import io
import math


def encode_message(state, metadata):
    import torch

    stream = io.BytesIO()
    torch.save({"state_dict": state, "metadata": metadata}, stream)
    return stream.getvalue()


def decode_message(payload):
    import torch

    return torch.load(io.BytesIO(payload), map_location="cpu", weights_only=True)


def measure_round_cost(config, selected_clients, messages, cost_model):
    network = cost_model["network_assumptions"]
    reference_step = cost_model["reference_train_step_seconds"]
    server = cost_model["server_round_seconds"]
    if reference_step <= 0 or server < 0:
        raise ValueError("Invalid diagnostic timing coefficients.")
    times, up_bytes, down_bytes = {}, 0, 0
    for client in selected_clients:
        download, upload = messages[client.client_id]
        if type(download) is not int or type(upload) is not int or min(download, upload) < 0:
            raise ValueError("Communication must count non-negative serialized byte sizes.")
        up_bytes += upload
        down_bytes += download
        times[client.client_id] = (
            download * 8 / (network["downlink_mbps"] * 1e6)
            + config["training"]["local_steps"] * reference_step * client.compute_time_multiplier
            + upload * 8 / (network["uplink_mbps"] * 1e6) + network["rtt_ms"] / 1000)
    duration = server + max(times.values(), default=0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid simulated duration.")
    return {"sim_seconds": duration, "up_bytes": up_bytes, "down_bytes": down_bytes,
            "training_steps": config["training"]["local_steps"] * len(selected_clients),
            "client_seconds": times,
            "synchronization_wait_seconds": sum(max(times.values()) - value for value in times.values())}
