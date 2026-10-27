"""Fixed-step local SGD and equal-client aggregation for FedAvg-U / FedProx-U."""


def train_local(model, dataset, generator, config, *, proximal_mu=0.0,
                server_control=None, client_control=None):
    import time
    import torch

    settings = config["training"]
    if settings["optimizer"] != "sgd" or proximal_mu < 0:
        raise ValueError("Only non-negative-mu plain SGD is implemented.")
    x, y = dataset
    reference = [parameter.detach().clone() for parameter in model.parameters()]
    optimizer = torch.optim.SGD(model.parameters(), lr=settings["initial_learning_rate"])
    losses, squared_losses, step_seconds = [], [], []
    model.train()
    for _ in range(settings["local_steps"]):
        ids = torch.randint(len(y), (settings["batch_size"],), generator=generator)
        started = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        per_example = torch.nn.functional.cross_entropy(model(x[ids]), y[ids], reduction="none")
        objective = per_example.mean()
        if proximal_mu:
            objective = objective + proximal_mu / 2 * sum(
                (parameter - initial).square().sum()
                for parameter, initial in zip(model.parameters(), reference))
        if not torch.isfinite(objective):
            raise ValueError("Non-finite local objective.")
        objective.backward()
        if server_control is not None:
            if client_control is None or proximal_mu:
                raise ValueError("SCAFFOLD requires client controls and no proximal term.")
            for name, parameter in model.named_parameters():
                parameter.grad.add_(server_control[name] - client_control[name])
        if any(parameter.grad is None or not torch.isfinite(parameter.grad).all()
               for parameter in model.parameters()):
            raise ValueError("Invalid local gradients.")
        optimizer.step()
        step_seconds.append(time.perf_counter() - started)
        losses.append(float(per_example.detach().mean()))
        squared_losses.append(float(per_example.detach().square().mean()))
    return {"loss": sum(losses) / len(losses), "steps": settings["local_steps"],
            "loss_rms": (sum(squared_losses) / len(squared_losses)) ** 0.5,
            "step_seconds": step_seconds}


def aggregate_equal(states, weights=None):
    import torch

    if not states:
        raise ValueError("Cannot aggregate an empty client set.")
    if weights is not None:
        import math
        if (len(weights) != len(states) or any(not math.isfinite(w) or w <= 0 for w in weights)):
            raise ValueError("Aggregation weights must be finite positive values for each client.")
        weights = torch.tensor(weights, dtype=torch.float64)
        weights = weights / weights.sum()
    keys = list(states[0])
    if any(list(state) != keys for state in states):
        raise ValueError("Mismatching model state keys.")
    result = {}
    for key in keys:
        values = [state[key] for state in states]
        if any(value.shape != values[0].shape or value.dtype != values[0].dtype for value in values):
            raise ValueError("Mismatching model parameter shapes/dtypes.")
        if not values[0].is_floating_point():
            raise ValueError("This MLP aggregator only supports floating-point parameters.")
        if weights is None:
            result[key] = torch.stack(values).mean(0)
        else:
            result[key] = sum(value * float(weight) for value, weight in zip(values, weights))
        if not torch.isfinite(result[key]).all():
            raise ValueError("Non-finite aggregated parameters.")
    return result
