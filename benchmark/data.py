"""Audited raw-record HAPT preparation; reserved evaluation splits stay separate."""

import hashlib
import json
import random
import re
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from flbench.repository import CONFIG, MANIFEST, file_hash, load_json

SOURCE_URL = ("https://archive.ics.uci.edu/static/public/341/"
              "smartphone+based+recognition+of+human+activities+and+postural+transitions.zip")
SOURCE_SHA256 = "4ac4ae064227c07045a99551876b54d204837e995e298b6488559e209b3deb09"
CACHE = "data/processed/hapt-v1"


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def array_hash(x, y) -> str:
    return hashlib.sha256(x.astype("<f4").tobytes() + y.astype("<i8").tobytes()).hexdigest()


def window_features(windows: np.ndarray) -> np.ndarray:
    """Channel-major: mean, std, min, max, median, IQR, mean abs diff, RMS."""
    if windows.ndim != 3 or windows.shape[2] != 6 or windows.shape[1] < 2:
        raise ValueError("Expected [windows, samples >= 2, 6 sensor channels].")
    values = [windows.mean(1), windows.std(1), windows.min(1), windows.max(1),
              np.median(windows, axis=1),
              np.quantile(windows, 0.75, axis=1) - np.quantile(windows, 0.25, axis=1),
              np.abs(np.diff(windows, axis=1)).mean(1), np.sqrt((windows ** 2).mean(1))]
    features = np.stack(values, axis=2).reshape(len(windows), 48).astype(np.float32)
    if not np.isfinite(features).all():
        raise ValueError("Non-finite raw features.")
    return features


def audit_intervals(windows: list[dict]) -> None:
    by_record = defaultdict(list)
    for window in windows:
        if window["stop"] <= window["start"]:
            raise ValueError("Invalid raw-sample interval.")
        by_record[(window["client"], window["experiment"])].append(window)
    for record, spans in by_record.items():
        spans.sort(key=lambda row: (row["start"], row["stop"]))
        for left, right in zip(spans, spans[1:]):
            if left["stop"] > right["start"]:
                raise ValueError(f"Overlapping raw samples in record {record}: {left}, {right}")


def fetch_archive(root: Path, *, download: bool = True) -> Path:
    destination = root / "data/raw/hapt/hapt_uci.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        if not download:
            raise FileNotFoundError("HAPT archive is missing; run prepare_data.py with network access.")
        temporary = destination.with_suffix(".download")
        with urllib.request.urlopen(SOURCE_URL, timeout=90) as source, temporary.open("wb") as output:
            while chunk := source.read(2**20):
                output.write(chunk)
        if file_hash(temporary) != SOURCE_SHA256:
            raise ValueError("UCI archive changed; review its contents/checksum before updating the pin.")
        temporary.replace(destination)
    if file_hash(destination) != SOURCE_SHA256:
        raise ValueError("Local HAPT archive does not match the observed/pinned archive checksum.")
    return destination


def prepare_data(root: Path, *, download: bool = True) -> dict:
    config = load_json(root / CONFIG)
    length, stride = config["split"]["window_length"], config["split"]["stride"]
    if stride != length:
        raise ValueError("This audited protocol requires non-overlapping windows.")
    archive_path = fetch_archive(root, download=download)
    raw = root / "data/raw/hapt/extracted"
    raw.mkdir(parents=True, exist_ok=True)
    sources = []
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if not (re.fullmatch(r"RawData/(acc|gyro)_exp\d{2}_user\d{2}\.txt", name)
                    or name in {"RawData/labels.txt", "README.txt", "activity_labels.txt"}):
                continue
            target = raw / name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = archive.read(name)
            target.write_bytes(content)
            sources.append({"path": name, "bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest()})
    labels = np.loadtxt(raw / "RawData/labels.txt", dtype=np.int64)
    records = defaultdict(set)
    for experiment, client, activity, start, end in labels:
        records[int(client)].add(int(experiment))
    clients = sorted(records)
    if clients != list(range(1, config["dataset"]["num_clients"] + 1)):
        raise ValueError("Unexpected client identities in real HAPT records.")
    rows = defaultdict(list)
    for row in labels:
        experiment, client, activity, start, end = map(int, row)
        if activity <= 6:
            rows[(client, experiment)].append((activity, start, end))
    features, targets = defaultdict(list), defaultdict(list)
    windows, client_summaries = [], []
    for client in clients:
        first = min(records[client])
        seen_validation = set()
        for experiment in sorted(records[client]):
            suffix = f"exp{experiment:02d}_user{client:02d}.txt"
            acc = np.loadtxt(raw / "RawData" / ("acc_" + suffix), dtype=np.float64)
            gyro = np.loadtxt(raw / "RawData" / ("gyro_" + suffix), dtype=np.float64)
            if acc.shape != gyro.shape or acc.shape[1] != 3 or not np.isfinite(acc).all() or not np.isfinite(gyro).all():
                raise ValueError(f"Invalid paired sensor records for {suffix}.")
            signal = np.concatenate((acc, gyro), axis=1)
            for activity, start, end in sorted(rows[(client, experiment)], key=lambda row: row[1]):
                if not 1 <= start < end <= len(signal):
                    raise ValueError("Activity annotation exceeds raw sensor record.")
                if experiment == first:
                    split = "train"
                elif activity not in seen_validation:
                    split = "validation"
                    seen_validation.add(activity)
                else:
                    split = "test"
                # Conservative interior: safe for both common inclusive label conventions.
                # Treat labels as one-based inclusive, then discard one sample at either edge.
                starts = list(range(start, end - 1 - length + 1, stride))
                if not starts:
                    raise ValueError(f"Activity segment too short: client={client}, activity={activity}")
                sliced = np.stack([signal[index:index + length] for index in starts])
                key = (client, split)
                features[key].append(window_features(sliced))
                targets[key].extend([activity - 1] * len(starts))
                windows.extend({"client": client, "experiment": experiment, "split": split,
                                "label": activity - 1, "start": index, "stop": index + length}
                               for index in starts)
        if seen_validation != set(range(1, 7)):
            raise ValueError(f"Client {client} is missing a validation activity.")
    audit_intervals(windows)
    arrays = {}
    for key in features:
        x = np.concatenate(features[key]).astype(np.float32)
        y = np.asarray(targets[key], dtype=np.int64)
        if set(y.tolist()) != set(range(6)):
            raise ValueError(f"Missing class support in {key}.")
        arrays[key] = (x, y)
    train_pool = np.concatenate([arrays[(client, "train")][0] for client in clients])
    mean, std = train_pool.mean(0), train_pool.std(0)
    std = np.where(std < 1e-6, 1.0, std).astype(np.float32)
    cache = root / CACHE
    cache.mkdir(parents=True, exist_ok=True)
    digests = []
    for client in clients:
        summary = {"client_id": client, "experiments": sorted(records[client]), "splits": {}}
        directory = cache / f"client-{client:02d}"
        directory.mkdir(exist_ok=True)
        for split in ("train", "validation", "test"):
            x, y = arrays[(client, split)]
            x = ((x - mean) / std).astype(np.float32)
            np.savez_compressed(directory / f"{split}.npz", x=x, y=y)
            digest = array_hash(x, y)
            summary["splits"][split] = {"windows": len(y),
                                         "class_counts": np.bincount(y, minlength=6).tolist(),
                                         "array_sha256": digest}
            digests.append({"client": client, "split": split, "sha256": digest})
        client_summaries.append(summary)
    validation_clients = clients.copy()
    random.Random(config["split"]["client_split_seed"]).shuffle(validation_clients)
    search = sorted(validation_clients[:config["split"]["search_validation_clients"]])
    confirmation = sorted(set(clients) - set(search))
    split_contract = {"rule": "first_record_train_later_first_activity_segment_validation_rest_test",
                      "window_length": length, "stride": stride, "boundary_guard_samples": 1,
                      "label_index_assumption": "one_based_inclusive_conservative_interior",
                      "feature_order": "channel_major_mean_std_min_max_median_iqr_absdiff_rms",
                      "normalization": "train_only_global_zscore",
                      "search_validation_clients": search, "confirmation_validation_clients": confirmation}
    data_hash = canonical_hash({"source": SOURCE_SHA256, "split": split_contract,
                                "scaler": {"mean": mean.tolist(), "std": std.tolist()},
                                "arrays": digests})
    (cache / "normalization.json").write_text(json.dumps({"fit_split": "train", "mean": mean.tolist(),
                                                          "std": std.tolist()}, indent=2) + "\n", encoding="utf-8")
    audit_path = cache / "raw_windows.json"
    audit_path.write_text(json.dumps(windows, separators=(",", ":")) + "\n", encoding="utf-8")
    manifest = {"status": "ready", "dataset": "UCI HAPT raw records", "content_sha256": data_hash,
                "source_url": SOURCE_URL, "archive_sha256": SOURCE_SHA256,
                "source_files": sorted(sources, key=lambda row: row["path"]),
                "clients": client_summaries, "overlap_audit_passed": True,
                "raw_window_audit_sha256": file_hash(audit_path), "split_contract": split_contract,
                "total_windows": {split: sum(item["splits"][split]["windows"] for item in client_summaries)
                                  for split in ("train", "validation", "test")}}
    previous = load_json(root / MANIFEST)
    if previous["status"] == "ready" and previous["content_sha256"] != data_hash:
        raise ValueError("Rebuilt data differs from the audited manifest; review/version the data protocol before replacing it.")
    (root / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    config["dataset"]["audit_status"] = "ready"
    (root / CONFIG).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return manifest


@dataclass
class PreparedData:
    train: dict
    validation: dict
    manifest: dict
    scenario: str
    evaluation_stage: str = "development"


def redistribute_near_iid(train: dict, seed: int) -> dict:
    """Stratified proportional allocation, preserving exact client and class totals."""
    import torch

    ids = sorted(train)
    x = torch.cat([train[client][0] for client in ids])
    y = torch.cat([train[client][1] for client in ids])
    generator = torch.Generator().manual_seed(seed)
    capacities = np.array([len(train[client][1]) for client in ids], dtype=np.int64)
    assigned = [[] for _ in ids]
    for label in range(6):
        positions = torch.where(y == label)[0]
        positions = positions[torch.randperm(len(positions), generator=generator)].tolist()
        total = int(capacities.sum())
        if not total:
            break
        quotas = len(positions) * capacities // total
        fractions = len(positions) * capacities % total
        tie_order = torch.randperm(len(ids), generator=generator).tolist()
        eligible = sorted(tie_order, key=lambda index: -int(fractions[index]))
        missing = len(positions) - int(quotas.sum())
        for index in eligible:
            if missing and quotas[index] < capacities[index]:
                quotas[index] += 1
                missing -= 1
        if missing:
            raise ValueError("Cannot allocate stratified training data within capacities.")
        offset = 0
        for index, quota in enumerate(quotas):
            assigned[index].extend(positions[offset:offset + int(quota)])
            offset += int(quota)
        capacities -= quotas
    if capacities.any():
        raise ValueError("Stratified assignment did not preserve per-client training sizes.")
    result = {}
    for client, indices in zip(ids, assigned):
        positions = torch.tensor(indices, dtype=torch.int64)
        positions = positions[torch.randperm(len(positions), generator=generator)]
        result[client] = (x[positions].clone(), y[positions].clone())
    return result


def load_prepared(root: Path, *, scenario: str, evaluation_stage: str = "development", seed: int = 11,
                  campaign: Path | None = None) -> PreparedData:
    import torch

    config, manifest = load_json(root / CONFIG), load_json(root / MANIFEST)
    if evaluation_stage not in {"development", "confirmation", "test"}:
        raise ValueError("Unknown evaluation stage.")
    if evaluation_stage != "development":
        from flbench.repository import protocol_hash
        if campaign is None:
            raise ValueError("Reserved labels require an explicitly frozen campaign.")
        access = load_json(campaign)
        if (access.get("status") != "frozen" or access.get("stage") != evaluation_stage
                or access.get("protocol_hash") != protocol_hash(root)
                or not access.get("frozen_run_matrix") or not access.get("candidate_config_hash")):
            raise ValueError("Reserved-stage campaign is not frozen for this protocol.")
    if scenario not in config["scenarios"] or manifest["status"] != "ready":
        raise ValueError("Unknown scenario or HAPT data not prepared.")
    train, validation = {}, {}
    if evaluation_stage == "development":
        allowed = set(manifest["split_contract"]["search_validation_clients"])
    elif evaluation_stage == "confirmation":
        allowed = set(manifest["split_contract"]["confirmation_validation_clients"])
    else:
        allowed = {item["client_id"] for item in manifest["clients"]}
    for summary in manifest["clients"]:
        client = summary["client_id"]
        for split, destination in (("train", train), ("validation", validation)):
            if split == "validation" and client not in allowed:
                continue
            actual_split = "test" if evaluation_stage == "test" and split == "validation" else split
            path = root / CACHE / f"client-{client:02d}" / f"{actual_split}.npz"
            with np.load(path, allow_pickle=False) as stored:
                x, y = stored["x"], stored["y"]
            if array_hash(x, y) != summary["splits"][actual_split]["array_sha256"]:
                raise ValueError(f"Modified cached split: {client}/{split}")
            destination[client] = (torch.from_numpy(x.copy()), torch.from_numpy(y.copy()))
    if scenario.startswith("near_iid"):
        train = redistribute_near_iid(train, seed)
    return PreparedData(train=train, validation=validation, manifest=manifest, scenario=scenario,
                        evaluation_stage=evaluation_stage)
