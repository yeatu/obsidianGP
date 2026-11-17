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
    # Compatibility overlay: Executor 1 represents an empty source interval as
    # line_end == line_start - 1. Preserve that exact coordinate in E2 rather
    # than silently inventing a line or modifying the E1 database.
    adapter_path = args.destination / "src" / "sfra_search" / "adapter.py"
    adapter_text = adapter_path.read_text(encoding="utf-8")
    legacy_validation = '''    for key in ("line_start", "line_end"):
        if isinstance(node[key], bool) or not isinstance(node[key], int) or node[key] < 1:
            raise ImportValidationError(f"{key} must be a positive 1-based integer")
    if node["line_end"] < node["line_start"]:
        raise ImportValidationError("line_end must be greater than or equal to line_start")
    raw_text = node["raw_text"]
    if not isinstance(raw_text, str):
        raise ImportValidationError("raw_text must be a string")
'''
    compatible_validation = '''    raw_text = node["raw_text"]
    if not isinstance(raw_text, str):
        raise ImportValidationError("raw_text must be a string")
    line_start = node["line_start"]
    line_end = node["line_end"]
    if isinstance(line_start, bool) or not isinstance(line_start, int) or line_start < 1:
        raise ImportValidationError("line_start must be a positive 1-based integer")
    if isinstance(line_end, bool) or not isinstance(line_end, int) or line_end < 0:
        raise ImportValidationError("line_end must be a non-negative 1-based line boundary")
    # Empty source spans have no inclusive line. E1 represents them as
    # line_end == line_start - 1 (for an empty file root: 1, 0).
    # Preserve this exact producer coordinate; do not invent a fake line.
    if line_end < line_start and not (raw_text == "" and line_end == line_start - 1):
        raise ImportValidationError(
            "line_end may precede line_start only for an empty source span"
        )
'''
    if legacy_validation in adapter_text:
        adapter_text = adapter_text.replace(legacy_validation, compatible_validation, 1)
        adapter_path.write_text(adapter_text, encoding="utf-8")
    elif compatible_validation not in adapter_text:
        raise RuntimeError("Unknown sfra_search adapter validation block; refusing an unsafe patch")

    # Keep a regression test alongside the published module, not only in this
    # build helper. It verifies both coordinate preservation and read-only DB use.
    test_path = args.destination / "tests" / "test_structural_runtime.py"
    if test_path.is_file():
        test_text = test_path.read_text(encoding="utf-8")
        test_marker = "def test_empty_source_span_preserves_executor1_zero_end_line("
        test_case = '''

def test_empty_source_span_preserves_executor1_zero_end_line(tmp_path):
    db_path = tmp_path / "structure.sqlite3"
    create_executor1_database(db_path)
    empty_hash = calculate_content_hash("")
    connection = sqlite3.connect(db_path)
    connection.execute(
        """UPDATE structural_nodes
           SET line_start=1, line_end=0, raw_text='', content_hash=?
           WHERE node_id='node_executor1_root'""",
        (empty_hash,),
    )
    connection.commit()
    connection.close()
    before = sha256_file(db_path)

    nodes, summary = load_current_nodes(db_path)
    root = next(node for node in nodes if node["node_id"] == "node_executor1_root")
    assert root["line_start"] == 1
    assert root["line_end"] == 0
    assert root["raw_text"] == ""
    assert root["content_hash"] == empty_hash

    source = get_source_node(db_path, "node_executor1_root", empty_hash)
    assert source is not None
    assert source["line_start"] == 1
    assert source["line_end"] == 0
    assert source["raw_text"] == ""
    assert sha256_file(db_path) == before
'''
        if test_marker not in test_text:
            test_path.write_text(test_text + test_case, encoding="utf-8")
    else:
        raise RuntimeError("Expected structural runtime test file is missing")

    files = sorted(
        str(p.relative_to(args.destination)).replace("\\\\", "/")
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
        "compatibility_overlays": ["empty_source_span_line_end=line_start-1; raw_text must be empty"],
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
