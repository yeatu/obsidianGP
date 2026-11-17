#!/usr/bin/env python3
"""Rebuild the published seven-part source archive and publish its source tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract(archive: Path, target: Path) -> None:
    target_resolved = target.resolve()
    with tarfile.open(archive, "r:xz") as tf:
        members = tf.getmembers()
        for member in members:
            rel = PurePosixPath(member.name)
            if rel.is_absolute() or ".." in rel.parts:
                raise RuntimeError(f"Unsafe archive member: {member.name}")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError(f"Unsupported archive member type: {member.name}")
            destination = (target / Path(*rel.parts)).resolve()
            if target_resolved not in destination.parents and destination != target_resolved:
                raise RuntimeError(f"Archive member escapes destination: {member.name}")
        tf.extractall(target, members=members)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-dir", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()

    parts = [args.implementation_dir / f"sfra-search-prototype.tar.xz.part{i:02d}" for i in range(7)]
    missing = [str(path) for path in parts if not path.is_file()]
    if missing:
        raise SystemExit("Missing archive parts: " + ", ".join(missing))

    archive = args.destination.parent / "sfra-search-prototype.rebuilt.tar.xz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("wb") as out:
        for part in parts:
            with part.open("rb") as src:
                shutil.copyfileobj(src, out)

    archive_sha = sha256(archive)
    extract_dir = args.destination.parent / "_sfra_archive_extract"
    shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True)
    safe_extract(archive, extract_dir)

    candidates = [p.parent for p in extract_dir.rglob("pyproject.toml")]
    if not candidates:
        candidates = [p.parent for p in extract_dir.rglob("setup.py")]
    if not candidates:
        raise SystemExit("No pyproject.toml or setup.py found in the published archive")

    candidates.sort(key=lambda p: (len(p.parts), len(str(p))))
    package_root = candidates[0]
    package_dirs = list(package_root.rglob("sfra_search"))
    if not any((p / "__init__.py").is_file() for p in package_dirs):
        raise SystemExit(f"sfra_search package directory not found below {package_root}")

    shutil.rmtree(args.destination, ignore_errors=True)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        package_root,
        args.destination,
        ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "*.pyc", "*.pyo"),
    )
    files = sorted(
        str(p.relative_to(args.destination)).replace("\\", "/")
        for p in args.destination.rglob("*") if p.is_file()
    )
    manifest = {
        "archive": "sfra-search-prototype.tar.xz assembled from seven tracked parts",
        "archive_sha256": "sha256:" + archive_sha,
        "part_sha256": {part.name: "sha1-git-blob:" + __import__("subprocess").check_output(
            ["git", "-C", str(args.implementation_dir.parents[5]), "hash-object", str(part)],
            text=True,
        ).strip() for part in parts},
        "source_root": ".",
        "files": files,
    }
    (args.destination / "SOURCE_ARCHIVE_PROVENANCE.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "destination": str(args.destination),
        "archive_sha256": "sha256:" + archive_sha,
        "file_count": len(files) + 1,
        "pyproject": str(args.destination / "pyproject.toml"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
