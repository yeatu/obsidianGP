from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3

import pytest

from sfra_indexer import (
    CloudIndexVerificationError,
    GitCommitSourceRevision,
    ImmutableImportSourceRevision,
    index_vault,
    parse_cloud_index_attestation,
    verify_materialized_cloud_index,
)


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _inventory(root):
    docs = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".md":
            raw = path.read_bytes()
            docs.append({
                "path": path.relative_to(root).as_posix(),
                "byte_size": len(raw),
                "sha256": _sha(raw),
            })
    docs.sort(key=lambda row: row["path"].encode("utf-8"))
    return _canonical({"format": "sfra.e1.markdown-inventory.v1", "documents": docs})


def _fixture(tmp_path, source_revision=None):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested" / "note.md").write_bytes("# Заголовок\r\n\r\nТекст 🧪.\r\n".encode("utf-8"))
    (root / "empty.MD").write_bytes(b"")
    (root / "ignored.txt").write_text("not indexed", encoding="utf-8")

    result = index_vault(root, tmp_path / "sidecar")
    db_path = Path(result.database_path)
    inventory = _inventory(root)
    connection = sqlite3.connect(db_path)
    try:
        document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        active_document_count = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE status='active'"
        ).fetchone()[0]
        node_count = connection.execute("SELECT COUNT(*) FROM structural_nodes").fetchone()[0]
        active_node_count = connection.execute(
            "SELECT COUNT(*) FROM structural_nodes "
            "WHERE status IN ('active','ambiguous') AND stale_generation IS NULL"
        ).fetchone()[0]
        passage_count = connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0]
        parser_rows = connection.execute(
            "SELECT DISTINCT parser_name, parser_version FROM documents WHERE status='active'"
        ).fetchall()
    finally:
        connection.close()

    parser_identities = [
        {"name": name, "version": version}
        for name, version in sorted(
            parser_rows, key=lambda pair: (pair[0].encode("utf-8"), pair[1].encode("utf-8"))
        )
    ]
    database = db_path.read_bytes()
    if source_revision is None:
        source_revision = {"kind": "git_commit", "commit_sha": "a" * 40}
    attestation = {
        "attestation_version": 1,
        "format": "sfra.e1.cloud-index-attestation.v1",
        "source_revision": source_revision,
        "markdown_inventory": {
            "format": "sfra.e1.markdown-inventory.v1",
            "path": "markdown-inventory.json",
            "sha256": _sha(inventory),
            "document_count": len(json.loads(inventory)["documents"]),
        },
        "indexer_identity": {
            "name": "sfra-structural-indexer",
            "version": importlib.metadata.version("sfra-structural-indexer"),
        },
        "parser_identities": parser_identities,
        "sqlite_schema_identity": {"engine": "sqlite", "schema_info_version": 2},
        "database": {
            "path": "state/structure.sqlite3",
            "sha256": _sha(database),
            "byte_size": len(database),
        },
        "counts": {
            "document_count": document_count,
            "active_document_count": active_document_count,
            "node_count": node_count,
            "active_node_count": active_node_count,
            "passage_count": passage_count,
        },
    }
    return root, db_path, inventory, attestation


def _verify(root, db_path, inventory, attestation):
    return verify_materialized_cloud_index(
        db_path, root, attestation=_canonical(attestation), markdown_inventory=inventory
    )


def test_verifies_git_backed_materialized_index_and_preserves_database_bytes(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    before = db_path.read_bytes()

    report = _verify(root, db_path, inventory, attestation)

    assert report.source_revision == GitCommitSourceRevision("a" * 40)
    assert report.schema_info_version == 2
    assert report.markdown_document_count == 2
    assert report.active_document_count == 2
    assert report.database_sha256 == _sha(before)
    assert db_path.read_bytes() == before


def test_immutable_import_revision_is_opaque_and_never_coerced(tmp_path):
    import_id = "vault-import:opaque:Ω-2026-11-19"
    root, db_path, inventory, attestation = _fixture(
        tmp_path, {"kind": "immutable_import", "import_id": import_id}
    )

    report = _verify(root, db_path, inventory, attestation)

    assert report.source_revision == ImmutableImportSourceRevision(import_id)
    assert report.source_revision.to_dict() == {
        "kind": "immutable_import", "import_id": import_id
    }


def test_attestation_rejects_duplicate_keys_and_noncanonical_json():
    with pytest.raises(CloudIndexVerificationError) as duplicate:
        parse_cloud_index_attestation(b'{"format":"x","format":"y"}')
    assert duplicate.value.code == "attestation_invalid"

    with pytest.raises(CloudIndexVerificationError) as noncanonical:
        parse_cloud_index_attestation(b'{ "format": "x" }')
    assert noncanonical.value.code == "attestation_invalid"


def test_rejects_source_tree_drift_against_inventory(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    (root / "nested" / "note.md").write_bytes(b"# changed\n")

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "inventory_mismatch"


def test_rejects_database_digest_mismatch_before_sqlite_inspection(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    db_path.write_bytes(db_path.read_bytes() + b"x")

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "database_digest_mismatch"


def test_rejects_parser_identity_mismatch(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    attestation["parser_identities"] = [{"name": "other-parser", "version": "0"}]

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "parser_identity_mismatch"


def test_rejects_corrupt_node_even_when_database_digest_is_recomputed(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE structural_nodes SET content_hash=? WHERE node_type='paragraph'",
            ("sha256:" + "0" * 64,),
        )
        connection.commit()
    finally:
        connection.close()
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "node_integrity_failure"


def test_rejects_schema_version_mismatch_without_migration(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("UPDATE schema_info SET schema_version=1 WHERE singleton=1")
        connection.commit()
    finally:
        connection.close()
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "schema_mismatch"
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT schema_version FROM schema_info WHERE singleton=1"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_rejects_symlink_in_materialized_tree(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    target = root / "nested" / "note.md"
    link = root / "linked.md"
    link.symlink_to(target)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "filesystem_unsafe"


def test_rejects_ambiguous_or_mutable_import_identifiers(tmp_path):
    for import_id in ("", "latest", " current ", "\x00import"):
        with pytest.raises(CloudIndexVerificationError):
            parse_cloud_index_attestation(_canonical({
                "attestation_version": 1,
                "format": "sfra.e1.cloud-index-attestation.v1",
                "source_revision": {"kind": "immutable_import", "import_id": import_id},
                "markdown_inventory": {
                    "format": "sfra.e1.markdown-inventory.v1",
                    "path": "markdown-inventory.json",
                    "sha256": "sha256:" + "0" * 64,
                    "document_count": 0,
                },
                "indexer_identity": {"name": "sfra-structural-indexer", "version": "0.2.0"},
                "parser_identities": [],
                "sqlite_schema_identity": {"engine": "sqlite", "schema_info_version": 2},
                "database": {
                    "path": "state/structure.sqlite3",
                    "sha256": "sha256:" + "0" * 64,
                    "byte_size": 0,
                },
                "counts": {
                    "document_count": 0, "active_document_count": 0, "node_count": 0,
                    "active_node_count": 0, "passage_count": 0,
                },
            }))
