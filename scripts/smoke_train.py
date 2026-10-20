"""Small synthetic CPU training check; never a HAPT or FL benchmark result."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

# Apply before loading numerical libraries. These values match the CPU smoke config.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import sklearn
import torch
from sklearn.metrics import accuracy_score, f1_score

from flbench.repository import file_hash, find_root, load_json
from flbench.environment import configure_cpu_runtime


def run_smoke(root: Path, config_path: Path, output: Path) -> dict:
    config = load_json(config_path)
    if config["purpose"] != "synthetic_environment_smoke_only" or config["device"] != "cpu":
        raise ValueError("This test supports synthetic CPU environment validation only.")
    if (config["input_features"], config["hidden_features"], config["num_classes"]) != (48, 64, 6):
        raise ValueError("Smoke model must match the planned 48 -> 64 -> 6 architecture.")
    configure_cpu_runtime(root, seed=config["seed"])
    rng = np.random.default_rng(config["seed"])
    centers = rng.normal(0, 2, (config["num_classes"], config["input_features"])).astype(np.float32)

    def dataset(count):
        if count % config["num_classes"]:
            raise ValueError("Synthetic sample counts must be divisible by the class count.")
        labels = np.tile(np.arange(config["num_classes"], dtype=np.int64), count // config["num_classes"])
        rng.shuffle(labels)
        features = centers[labels] + rng.normal(0, config["noise_std"], (count, config["input_features"]))
        return torch.from_numpy(features.astype(np.float32)), torch.from_numpy(labels)

    train_x, train_y = dataset(config["train_samples"])
    test_x, test_y = dataset(config["test_samples"])

    def build():
        model = torch.nn.Sequential(torch.nn.Linear(48, 64), torch.nn.ReLU(), torch.nn.Linear(64, 6))
        optimizer = torch.optim.SGD(model.parameters(), lr=config["learning_rate"])
        return model, optimizer

    criterion = torch.nn.CrossEntropyLoss()
    model, optimizer = build()
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count != 3526:
        raise AssertionError("Model parameter count differs from the research plan.")
    batch_rng = torch.Generator(device="cpu").manual_seed(config["seed"] + 1)

    def train_steps(active_model, active_optimizer, generator, count):
        active_model.train()
        for _ in range(count):
            ids = torch.randint(len(train_y), (config["batch_size"],), generator=generator)
            active_optimizer.zero_grad(set_to_none=True)
            loss = criterion(active_model(train_x[ids]), train_y[ids])
            if not torch.isfinite(loss):
                raise AssertionError("Non-finite training loss.")
            loss.backward()
            if any(not torch.isfinite(parameter.grad).all() for parameter in active_model.parameters()):
                raise AssertionError("Non-finite gradient.")
            active_optimizer.step()

    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with torch.no_grad():
        initial_loss = criterion(model(train_x), train_y).item()
    train_steps(model, optimizer, batch_rng, config["checkpoint_step"])
    checkpoint_path = output / "checkpoint.pt"
    torch.save({"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                "batch_rng": batch_rng.get_state(), "torch_rng": torch.get_rng_state(),
                "completed_steps": config["checkpoint_step"]}, checkpoint_path)
    remainder = config["gradient_steps"] - config["checkpoint_step"]
    if remainder <= 0:
        raise ValueError("Checkpoint must precede the final training step.")
    train_steps(model, optimizer, batch_rng, remainder)
    model.eval()
    with torch.no_grad():
        final_loss = criterion(model(train_x), train_y).item()
        predictions = model(test_x).argmax(dim=1).numpy()
    macro_f1 = float(f1_score(test_y.numpy(), predictions, labels=list(range(6)), average="macro", zero_division=0))
    accuracy = float(accuracy_score(test_y.numpy(), predictions))

    restored_model, restored_optimizer = build()
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    restored_model.load_state_dict(checkpoint["model"])
    restored_optimizer.load_state_dict(checkpoint["optimizer"])
    restored_rng = torch.Generator(device="cpu")
    restored_rng.set_state(checkpoint["batch_rng"])
    torch.set_rng_state(checkpoint["torch_rng"])
    train_steps(restored_model, restored_optimizer, restored_rng, remainder)
    resume_equal = all(torch.equal(value, restored_model.state_dict()[key])
                       for key, value in model.state_dict().items())
    restored_model.eval()
    with torch.no_grad():
        predictions_equal = torch.equal(model(test_x), restored_model(test_x))
    checks = {
        "loss_decreased": final_loss < initial_loss * config["maximum_final_to_initial_loss_ratio"],
        "test_macro_f1_passed": macro_f1 >= config["minimum_test_macro_f1"],
        "resume_weights_exactly_equal": resume_equal,
        "resume_predictions_exactly_equal": predictions_equal,
        "cpu_only_build": torch.version.cuda is None,
        "project_virtual_environment": Path(sys.prefix).resolve() == (root / ".venv").resolve(),
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "purpose": config["purpose"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "metrics": {"initial_train_loss": initial_loss, "final_train_loss": final_loss,
                    "synthetic_test_macro_f1": macro_f1, "synthetic_test_accuracy": accuracy,
                    "training_and_resume_wall_seconds": time.perf_counter() - started},
        "model": {"layers": [48, 64, 6], "parameters": parameter_count},
        "config": config,
        "environment": {
            "python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(), "machine": platform.machine(),
            "uv": subprocess.check_output(["uv", "--version"], text=True).strip().split()[1],
            "numpy": np.__version__, "torch": torch.__version__, "scikit-learn": sklearn.__version__,
            "torch_cuda_build": torch.version.cuda, "torch_num_threads": torch.get_num_threads(),
            "torch_num_interop_threads": torch.get_num_interop_threads(),
            "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
            "installed_distributions": dict(sorted((dist.metadata["Name"], dist.version)
                                                    for dist in metadata.distributions())),
        },
        "provenance": {
            "config_sha256": file_hash(config_path), "uv_lock_sha256": file_hash(root / "uv.lock"),
            "checkpoint_sha256": file_hash(checkpoint_path),
            "synthetic_arrays_sha256": hashlib.sha256(b"".join(array.numpy().tobytes()
                                                               for array in (train_x, train_y, test_x, test_y))).hexdigest(),
        },
        "limitations": "Synthetic single-process CPU training only; not HAPT, FL correctness, or calibrated benchmark timing.",
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "metrics": report["metrics"], "checks": checks,
                      "report": str(report_path)}, indent=2))
    if report["status"] != "passed":
        raise AssertionError("Environment smoke failed; inspect report.json.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/environment/smoke.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/environment-smoke"))
    args = parser.parse_args()
    root = find_root()
    run_smoke(root, (root / args.config).resolve(), (root / args.output).resolve())


if __name__ == "__main__":
    main()
