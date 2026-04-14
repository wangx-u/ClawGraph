#!/usr/bin/env python3
"""Prepare a local SWE-bench instance checkout for local-environment smoke runs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from datasets import load_dataset


DATASET_MAPPING = {
    "full": "princeton-nlp/SWE-Bench",
    "verified": "princeton-nlp/SWE-Bench_Verified",
    "lite": "princeton-nlp/SWE-Bench_Lite",
    "multimodal": "princeton-nlp/SWE-Bench_Multimodal",
    "multilingual": "swe-bench/SWE-Bench_Multilingual",
    "smith": "SWE-bench/SWE-smith",
    "_test": "klieret/swe-bench-dummy-test-dataset",
    "rebench": "nebius/SWE-rebench",
}


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def _resolve_instance(*, subset: str, split: str, instance_spec: str) -> dict:
    dataset_path = DATASET_MAPPING.get(subset, subset)
    instances = list(load_dataset(dataset_path, split=split))
    if instance_spec.isnumeric():
        instance_index = int(instance_spec)
        instance = sorted(instances, key=lambda item: item["instance_id"])[instance_index]
    else:
        matching = [item for item in instances if item["instance_id"] == instance_spec]
        if not matching:
            raise ValueError(f"instance not found: {instance_spec}")
        instance = matching[0]
    return dict(instance)


def _ensure_repo_checkout(*, repo_dir: Path, repo_name: str, base_commit: str, force: bool) -> None:
    if not repo_dir.exists():
        repo_dir.mkdir(parents=True, exist_ok=True)

    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        _run(["git", "init"], cwd=repo_dir)
        _run(["git", "remote", "add", "origin", f"https://github.com/{repo_name}.git"], cwd=repo_dir)

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip() and not force:
        raise RuntimeError(
            f"existing checkout is dirty: {repo_dir}. Re-run with --force to overwrite the worktree."
        )

    try:
        _run(["git", "fetch", "--depth", "1", "origin", base_commit], cwd=repo_dir)
        checkout_args = ["git", "checkout"]
        if force:
            checkout_args.append("--force")
        checkout_args.append("FETCH_HEAD")
        _run(checkout_args, cwd=repo_dir)
    except subprocess.CalledProcessError:
        _materialize_archive_checkout(
            repo_dir=repo_dir,
            repo_name=repo_name,
            base_commit=base_commit,
        )


def _materialize_archive_checkout(*, repo_dir: Path, repo_name: str, base_commit: str) -> None:
    archive_url = f"https://codeload.github.com/{repo_name}/tar.gz/{base_commit}"
    with tempfile.TemporaryDirectory() as tempdir:
        tempdir_path = Path(tempdir)
        archive_path = tempdir_path / "repo.tar.gz"
        extract_dir = tempdir_path / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(archive_url) as response, archive_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(extract_dir, filter="data")
        roots = [path for path in extract_dir.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError(f"unexpected archive layout for {archive_url}")
        shutil.rmtree(repo_dir, ignore_errors=True)
        repo_dir.mkdir(parents=True, exist_ok=True)
        for child in roots[0].iterdir():
            shutil.move(str(child), repo_dir / child.name)


def _ensure_venv(*, python_executable: str, venv_dir: Path) -> tuple[Path, Path]:
    if not (venv_dir / "bin" / "python").exists():
        _run([python_executable, "-m", "venv", str(venv_dir)])
    python_bin = venv_dir / "bin" / "python"
    pip_bin = venv_dir / "bin" / "pip"
    _run(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "pip",
            "wheel",
            "setuptools<81",
        ]
    )
    return python_bin, pip_bin


def _write_local_config(
    *,
    output_path: Path,
    repo_dir: Path,
    venv_dir: Path,
    timeout_seconds: int,
) -> None:
    path_parts = [
        str(venv_dir / "bin"),
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    content = "\n".join(
        [
            "environment:",
            '  environment_class: "local"',
            f'  cwd: "{repo_dir}"',
            f"  timeout: {timeout_seconds}",
            "  env:",
            f'    PATH: "{":".join(path_parts)}"',
            f'    VIRTUAL_ENV: "{venv_dir}"',
            '    PIP_DISABLE_PIP_VERSION_CHECK: "1"',
            '    PYTHONNOUSERSITE: "1"',
            "",
        ]
    )
    output_path.write_text(content, encoding="utf-8")


def _write_metadata(*, output_path: Path, instance: dict, repo_dir: Path, venv_dir: Path) -> None:
    payload = {
        "instance_id": instance["instance_id"],
        "repo": instance["repo"],
        "base_commit": instance["base_commit"],
        "problem_statement": instance["problem_statement"],
        "patch": instance.get("patch"),
        "test_patch": instance.get("test_patch"),
        "workspace": str(repo_dir),
        "venv": str(venv_dir),
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subset", default="lite")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--instance", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--install-editable", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    repo_dir = workdir / "testbed"
    venv_dir = workdir / ".localenv"
    config_path = workdir / "mini.local.yaml"
    metadata_path = workdir / "instance.json"

    instance = _resolve_instance(subset=args.subset, split=args.split, instance_spec=args.instance)
    _ensure_repo_checkout(
        repo_dir=repo_dir,
        repo_name=instance["repo"],
        base_commit=instance["base_commit"],
        force=args.force,
    )
    python_bin, _ = _ensure_venv(python_executable=args.python, venv_dir=venv_dir)
    if args.install_editable:
        _run([str(python_bin), "-m", "pip", "install", "-e", str(repo_dir)])
    _write_local_config(
        output_path=config_path,
        repo_dir=repo_dir,
        venv_dir=venv_dir,
        timeout_seconds=args.timeout,
    )
    _write_metadata(output_path=metadata_path, instance=instance, repo_dir=repo_dir, venv_dir=venv_dir)

    print(json.dumps({"config": str(config_path), "metadata": str(metadata_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
