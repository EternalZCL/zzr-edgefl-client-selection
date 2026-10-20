"""Shared CPU settings and validation of the uv-managed project environment."""

import os
import platform
import random
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

from flbench.repository import file_hash, load_json

RUNTIME_CONFIG = "configs/environment/runtime.json"


def configure_cpu_runtime(root: Path, seed: int) -> None:
    config = load_json(root / RUNTIME_CONFIG)
    for key, value in (("OMP_NUM_THREADS", "omp_num_threads"),
                       ("MKL_NUM_THREADS", "mkl_num_threads"),
                       ("OPENBLAS_NUM_THREADS", "openblas_num_threads")):
        os.environ[key] = str(config[value])
    import numpy as np
    import torch

    if config["device"] != "cpu" or config["dtype"] != "float32":
        raise ValueError("The shared profile requires CPU / float32.")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(config["torch_num_threads"])
    if torch.get_num_interop_threads() != config["torch_num_interop_threads"]:
        torch.set_num_interop_threads(config["torch_num_interop_threads"])
    torch.use_deterministic_algorithms(config["deterministic_algorithms"])
    torch.set_default_dtype(torch.float32)


def environment_errors(root: Path, *, check_sync: bool = True) -> list[str]:
    config = load_json(root / RUNTIME_CONFIG)
    errors = []
    if platform.python_version() != config["python"]:
        errors.append(f"Python must be {config['python']}; found {platform.python_version()}.")
    if platform.python_implementation() != "CPython":
        errors.append("The shared interpreter must be CPython.")
    if Path(sys.prefix).resolve() != (root / ".venv").resolve() or sys.prefix == sys.base_prefix:
        errors.append("Use this checkout's uv-managed .venv, via uv run --locked --exact.")
    venv_config = root / ".venv/pyvenv.cfg"
    if not venv_config.is_file() or f"uv = {config['uv']}" not in venv_config.read_text(encoding="utf-8"):
        errors.append(f"Create this checkout's .venv with uv {config['uv']}.")
    uv_version = subprocess.check_output(["uv", "--version"], text=True).strip().split()[1]
    if uv_version != config["uv"]:
        errors.append(f"uv must be {config['uv']}; found {uv_version}.")
    if errors:
        return errors  # Do not load binary libraries from the wrong interpreter/environment.
    if check_sync:
        result = subprocess.run(["uv", "sync", "--locked", "--check"], cwd=root,
                                capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            errors.append("Environment differs from uv.lock: " + (result.stderr or result.stdout).strip())
    if errors:
        return errors
    import torch

    if torch.version.cuda is not None:
        errors.append("The shared profile requires a CPU-only PyTorch build.")
    return errors


def environment_snapshot(root: Path) -> dict:
    config = load_json(root / RUNTIME_CONFIG)
    installed = dict(sorted((distribution.metadata["Name"], distribution.version)
                            for distribution in metadata.distributions()))
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "machine": platform.machine(), "implementation": platform.python_implementation(),
        "uv": subprocess.check_output(["uv", "--version"], text=True).strip().split()[1],
        "uv_lock_sha256": file_hash(root / "uv.lock"),
        "runtime_config_sha256": file_hash(root / RUNTIME_CONFIG),
        "profile": config["profile"], "installed_distributions": installed,
    }


def environment_policy_errors(root: Path) -> list[str]:
    """Check consistency of versioned settings without importing research dependencies."""
    config = load_json(root / RUNTIME_CONFIG)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    errors = []
    expected_python = "==" + config["python"]
    if ((root / ".python-version").read_text(encoding="utf-8").strip() != config["python"]
            or project["project"]["requires-python"] != expected_python
            or lock["requires-python"] != expected_python):
        errors.append("Python version differs between runtime policy, pin, pyproject and uv.lock.")
    if project["tool"]["uv"]["required-version"] != "==" + config["uv"]:
        errors.append("uv version differs between runtime policy and pyproject.")
    for requirement in project["project"]["dependencies"]:
        if "==" not in requirement:
            errors.append(f"Direct dependency must be pinned after smoke validation: {requirement}")
        else:
            name, version = requirement.split("==", 1)
            matches = [item for item in lock["package"] if item["name"] == name]
            if not matches or any(item["version"].split("+", 1)[0] != version for item in matches):
                errors.append(f"Direct dependency disagrees with uv.lock: {requirement}")
    smoke = load_json(root / "configs/environment/smoke.json")
    for key in ("device", "torch_num_threads", "torch_num_interop_threads", "deterministic_algorithms"):
        if smoke[key] != config[key]:
            errors.append(f"Smoke setting {key} differs from the shared runtime profile.")
    return errors
