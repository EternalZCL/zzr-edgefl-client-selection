"""Development-only evaluator; confirmation/final labels remain unavailable."""


def evaluate(model, dataset, stage="development"):
    import numpy as np
    import torch
    from sklearn.metrics import accuracy_score, f1_score

    if stage != "development":
        raise ValueError("Reserved confirmation/test evaluation is disabled in the bootstrap runner.")
    allowed = set(dataset.manifest["split_contract"]["search_validation_clients"])
    if set(dataset.validation) != allowed:
        raise ValueError("Evaluator received the wrong validation client set.")
    scores = []
    model.eval()
    with torch.no_grad():
        for client in sorted(allowed):
            x, y = dataset.validation[client]
            predictions = model(x).argmax(1).cpu().numpy()
            labels = y.cpu().numpy()
            scores.append({"client_id": client, "support": len(y),
                           "macro_f1": float(f1_score(labels, predictions, labels=list(range(6)),
                                                      average="macro", zero_division=0)),
                           "accuracy": float(accuracy_score(labels, predictions))})
    return {"scope": "search_validation", "num_clients": len(scores), "clients": scores,
            "mean_client_macro_f1": float(np.mean([row["macro_f1"] for row in scores]))}
