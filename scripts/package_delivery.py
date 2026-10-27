"""Build and verify a portable research package, including Git history and run artifacts."""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output.resolve()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip():
        raise ValueError("Commit final sources and summaries before packaging.")
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip()
    subprocess.run(["git", "bundle", "create", str(out / "ghj-project.bundle"), "--all"], cwd=root, check=True)
    subprocess.run(["git", "bundle", "verify", str(out / "ghj-project.bundle")], cwd=root, check=True)
    subprocess.run(["git", "archive", "--format=zip", "--output=" + str(out / "source.zip"), "HEAD"], cwd=root, check=True)
    entries = {}
    for name in ("研究报告.md", "研究报告.html", "研究报告.pdf", "results.csv", "results.json",
                 "交付说明.md", "PR说明.md", "ghj-project.bundle", "source.zip"):
        path = out / name
        if not path.is_file():
            raise ValueError("Missing deliverable: " + name)
        entries[name] = path
    entries["restore-project.ps1"] = root / "scripts/restore_delivery.ps1"
    entries["github-submit.ps1"] = root / "scripts/github_submit.ps1"
    for path in sorted((out / "figures").rglob("*")):
        if path.is_file():
            entries[path.relative_to(out).as_posix()] = path
    records = [json.loads(path.read_text(encoding="utf-8-sig")) for path in sorted((root / "agents/ghj/runs").glob("*.json"))]
    for record in records:
        archive = (root / record["artifact_uri"]).resolve()
        if not archive.is_relative_to(root / "artifacts") or sha256(archive) != record["artifact_sha256"]:
            raise ValueError("Artifact hash mismatch: " + record["run_id"])
        for path in sorted(archive.parent.rglob("*")):
            if path.is_file():
                entries[path.relative_to(root).as_posix()] = path
    for folder in (root / "data/processed/hapt-v1", root / "artifacts/federated-smoke", root / "artifacts/environment-smoke"):
        if not folder.is_dir() and "processed" in str(folder):
            raise ValueError("Missing offline data cache.")
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                entries[path.relative_to(root).as_posix()] = path
    manifest = {"format_version": 1, "delivery_commit": commit, "branch": branch,
                "research_code_commit": "51b2cec2e529a2ceb2ba0ba8f8b4664a3ca5015b",
                "protocol_hash": "aa3551b6b85b6074adcac1786f587a728a0d62fc3e041c4c4e6625b2d3be2fc0",
                "published_runs": len(records), "formal_complete": 175,
                "files": [{"path": name, "size": path.stat().st_size, "sha256": sha256(path)}
                          for name, path in sorted(entries.items())]}
    (out / "delivery-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name in ("restore-project.ps1", "github-submit.ps1"):
        (out / name).write_bytes(entries[name].read_bytes())
    destination = out / "ghj-complete-delivery.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(entries.items()):
            archive.write(path, name)
        archive.write(out / "delivery-manifest.json", "delivery-manifest.json")
    with zipfile.ZipFile(destination) as archive:
        for item in manifest["files"]:
            with archive.open(item["path"]) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                    raise ValueError("Packaged content mismatch: " + item["path"])
    names = ("ghj-complete-delivery.zip", "ghj-project.bundle", "source.zip", "delivery-manifest.json", "研究报告.pdf")
    (out / "SHA256SUMS.txt").write_text("".join(sha256(out / n) + "  " + n + "\n" for n in names), encoding="utf-8")
    print(json.dumps({"status": "verified", "delivery_commit": commit, "packaged_files": len(entries),
                      "bytes": destination.stat().st_size, "sha256": sha256(destination)}, indent=2))


if __name__ == "__main__":
    main()
