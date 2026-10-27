"""Fixed-label client-equal evaluation, with explicit reserved-stage contracts."""


def evaluate(model, dataset, stage=None):
    import numpy as np
    import torch
    from sklearn.metrics import accuracy_score, f1_score

    actual_stage = getattr(dataset, "evaluation_stage", "development")
    stage = actual_stage if stage is None else stage
    if stage != actual_stage:
        raise ValueError("Evaluation stage differs from the loaded data contract.")
    contract = dataset.manifest["split_contract"]
    if stage == "development":
        allowed, scope = set(contract["search_validation_clients"]), "search_validation"
    elif stage == "confirmation":
        allowed, scope = set(contract["confirmation_validation_clients"]), "confirmation_validation"
    elif stage == "test":
        allowed, scope = set(dataset.train), "final_test"
    else:
        raise ValueError("Unknown evaluation stage.")
    if set(dataset.validation) != allowed:
        raise ValueError("Evaluator received the wrong validation client set.")
    scores, all_labels, all_predictions = [], [], []
    with torch.no_grad():
        for client in sorted(allowed):
            current = model[client] if isinstance(model, dict) else model
            current.eval()
            x, y = dataset.validation[client]
            predictions = current(x).argmax(1).cpu().numpy()
            labels = y.cpu().numpy()
            scores.append({"client_id": client, "support": len(y),
                           "macro_f1": float(f1_score(labels, predictions, labels=list(range(6)),
                                                      average="macro", zero_division=0)),
                           "accuracy": float(accuracy_score(labels, predictions))})
            all_labels.extend(labels.tolist())
            all_predictions.extend(predictions.tolist())
    values = sorted(row["macro_f1"] for row in scores)
    return {"scope": scope, "num_clients": len(scores), "clients": scores,
            "mean_client_macro_f1": float(np.mean(values)),
            "tail_20_percent_macro_f1": float(np.mean(values[:max(1, len(values) // 5)])),
            "pooled_macro_f1": float(f1_score(all_labels, all_predictions, labels=list(range(6)),
                                             average="macro", zero_division=0))}
