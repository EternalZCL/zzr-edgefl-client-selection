"""Shared CPU MLP; randomness is configured by the caller before construction."""


def build_model(config):
    import torch

    values = config["model"]
    return torch.nn.Sequential(torch.nn.Linear(values["input_features"], values["hidden_features"]),
                               torch.nn.ReLU(),
                               torch.nn.Linear(values["hidden_features"], values["output_classes"]))
