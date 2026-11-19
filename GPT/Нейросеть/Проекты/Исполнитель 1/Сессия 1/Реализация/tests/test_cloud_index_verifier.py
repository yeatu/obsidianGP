from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3

import pytest

import sfra_indexer.cloud_index_verifier as cloud_verifier
from sfra_indexer import (
    CloudIndexVerificationError,
    GitCommitSourceRevision,
    ImmutableImportSourceRevision,
    SourceRevision,
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


def _verify(root, db_path, inventory, attestation, *, expected_source_revision=None):
    raw_attestation = _canonical(attestation)
    expected = expected_source_revision or parse_cloud_index_attestation(raw_attestation).source_revision
    return verify_materialized_cloud_index(
        db_path, root, expected_source_revision=expected,
        attestation=raw_attestation, markdown_inventory=inventory
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
    assert error.value.code == "node_content_mismatch"


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


def test_source_revision_failure_has_its_own_stable_code(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    attestation["source_revision"] = {"kind": "unknown_revision", "id": "x"}

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "source_revision_invalid"


def test_rejects_unexpected_schema_table(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unexpected_cloud_table (value TEXT)")
        connection.commit()
    finally:
        connection.close()
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "schema_mismatch"


def test_distinguishes_foreign_key_failure(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE structural_nodes SET document_pk=999999 "
            "WHERE node_pk=(SELECT MIN(node_pk) FROM structural_nodes)"
        )
        connection.commit()
    finally:
        connection.close()
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "foreign_key_failure"


def test_rejects_event_history_corruption_even_with_matching_database_digest(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE node_match_events SET event_type='not-an-e1-event' "
            "WHERE event_pk=(SELECT MIN(event_pk) FROM node_match_events)"
        )
        connection.commit()
    finally:
        connection.close()
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "node_history_mismatch"


def test_rejects_node_coordinate_corruption_even_with_matching_database_digest(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE structural_nodes SET char_start=char_start+1 "
            "WHERE node_pk=(SELECT MIN(node_pk) FROM structural_nodes)"
        )
        connection.commit()
    finally:
        connection.close()
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "node_span_mismatch"


def test_rejects_extra_markdown_file_and_invalid_utf8_markdown(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    (root / "extra.md").write_text("not indexed", encoding="utf-8")
    with pytest.raises(CloudIndexVerificationError) as extra:
        _verify(root, db_path, inventory, attestation)
    assert extra.value.code == "inventory_mismatch"

    (root / "extra.md").unlink()
    (root / "bad.md").write_bytes(b"\xff")
    with pytest.raises(CloudIndexVerificationError) as invalid:
        _verify(root, db_path, inventory, attestation)
    assert invalid.value.code == "filesystem_unsafe"


def test_rejects_malformed_inventory_bytes_without_partial_report(tmp_path):
    root, db_path, _inventory_bytes, attestation = _fixture(tmp_path)
    with pytest.raises(CloudIndexVerificationError) as error:
        verify_materialized_cloud_index(
            db_path, root,
            expected_source_revision=parse_cloud_index_attestation(_canonical(attestation)).source_revision,
            attestation=_canonical(attestation), markdown_inventory=b"\xff"
        )
    assert error.value.code == "inventory_invalid"
    assert str(root) not in str(error.value)


def test_verification_report_is_deterministic_for_identical_fixture(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    first = _verify(root, db_path, inventory, attestation)
    second = _verify(root, db_path, inventory, attestation)
    assert first == second


def test_verifier_has_no_provider_or_e3_import_dependency():
    import ast

    source = (Path(__file__).parents[1] / "sfra_indexer" / "cloud_index_verifier.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {
        name for name in imported
        if name.startswith(("sfra_context_integrations", "boto3", "botocore",
                            "google.cloud", "azure", "requests"))
        or name.endswith("cloud_snapshot_v2")
    }
    assert forbidden == set()


def test_detects_source_file_replacement_during_read(tmp_path, monkeypatch):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    target = root / "nested" / "note.md"
    os_module = __import__("os")
    original_read = os_module.read
    target_inode = target.stat().st_ino
    replaced = False

    def racing_read(fd, size):
        nonlocal replaced
        chunk = original_read(fd, size)
        if not replaced and os_module.fstat(fd).st_ino == target_inode:
            replaced = True
            target.unlink()
            target.write_bytes(b"replacement after open\n")
        return chunk

    monkeypatch.setattr("sfra_indexer.cloud_index_verifier.os.read", racing_read)
    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "filesystem_race"


def test_missing_materialized_root_has_safe_typed_failure(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    root.rename(tmp_path / "moved-vault")

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "filesystem_unsafe"
    assert str(root) not in str(error.value)
    assert error.value.__cause__ is None


def test_race_failure_does_not_retain_raw_os_exception(tmp_path, monkeypatch):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    target = root / "nested" / "note.md"
    os_module = __import__("os")
    original_read = os_module.read
    target_inode = target.stat().st_ino
    replaced = False

    def racing_read(fd, size):
        nonlocal replaced
        chunk = original_read(fd, size)
        if not replaced and os_module.fstat(fd).st_ino == target_inode:
            replaced = True
            target.unlink()
        return chunk

    monkeypatch.setattr("sfra_indexer.cloud_index_verifier.os.read", racing_read)
    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "filesystem_race"
    assert error.value.__cause__ is None
    assert str(root) not in str(error.value)


def _refresh_attestation(root, db_path, attestation):
    inventory = _inventory(root)
    connection = sqlite3.connect(db_path)
    try:
        counts = {
            "document_count": connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "active_document_count": connection.execute(
                "SELECT COUNT(*) FROM documents WHERE status='active'"
            ).fetchone()[0],
            "node_count": connection.execute("SELECT COUNT(*) FROM structural_nodes").fetchone()[0],
            "active_node_count": connection.execute(
                "SELECT COUNT(*) FROM structural_nodes "
                "WHERE status IN ('active','ambiguous') AND stale_generation IS NULL"
            ).fetchone()[0],
            "passage_count": connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0],
        }
        parsers = connection.execute(
            "SELECT DISTINCT parser_name, parser_version FROM documents WHERE status='active'"
        ).fetchall()
    finally:
        connection.close()
    attestation["markdown_inventory"]["sha256"] = _sha(inventory)
    attestation["markdown_inventory"]["document_count"] = len(json.loads(inventory)["documents"])
    attestation["parser_identities"] = [
        {"name": name, "version": version}
        for name, version in sorted(
            parsers, key=lambda pair: (pair[0].encode("utf-8"), pair[1].encode("utf-8"))
        )
    ]
    attestation["counts"] = counts
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)
    return inventory


def test_verifies_deleted_document_and_retained_node_history(tmp_path):
    root, db_path, _inventory_bytes, attestation = _fixture(tmp_path)
    note = root / "nested" / "note.md"
    note.write_text("# Revised\n\nA second indexed generation.\n", encoding="utf-8")
    index_vault(root, tmp_path / "sidecar")
    note.unlink()
    index_vault(root, tmp_path / "sidecar")

    inventory = _refresh_attestation(root, db_path, attestation)
    report = _verify(root, db_path, inventory, attestation)

    assert report.document_count == 2
    assert report.active_document_count == 1
    assert report.node_count > report.active_node_count


def test_rejects_corrupt_historical_node_version(tmp_path):
    root, db_path, _inventory_bytes, attestation = _fixture(tmp_path)
    note = root / "nested" / "note.md"
    note.write_text("# Revised\n\nA second indexed generation.\n", encoding="utf-8")
    index_vault(root, tmp_path / "sidecar")
    inventory = _refresh_attestation(root, db_path, attestation)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE node_versions SET raw_text='tampered history' "
            "WHERE node_version_pk=(SELECT MIN(node_version_pk) FROM node_versions)"
        )
        connection.commit()
    finally:
        connection.close()
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code in {"node_content_mismatch", "node_version_mismatch"}


def test_public_source_revision_union_is_exported():
    assert SourceRevision == (GitCommitSourceRevision | ImmutableImportSourceRevision)


def test_rejects_traversal_path_in_canonical_inventory(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    obj = json.loads(inventory)
    obj["documents"][0]["path"] = "../outside.md"
    forged_inventory = _canonical(obj)
    attestation["markdown_inventory"]["sha256"] = _sha(forged_inventory)
    attestation["markdown_inventory"]["document_count"] = len(obj["documents"])

    with pytest.raises(CloudIndexVerificationError) as error:
        verify_materialized_cloud_index(
            db_path, root,
            expected_source_revision=parse_cloud_index_attestation(_canonical(attestation)).source_revision,
            attestation=_canonical(attestation),
            markdown_inventory=forged_inventory,
        )
    assert error.value.code == "inventory_invalid"


def test_binds_attestation_to_exact_expected_git_source_revision(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    report = _verify(root, db_path, inventory, attestation)
    assert report.source_revision == GitCommitSourceRevision("a" * 40)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(
            root, db_path, inventory, attestation,
            expected_source_revision=GitCommitSourceRevision("b" * 40),
        )
    assert error.value.code == "source_revision_mismatch"


def test_binds_attestation_to_exact_opaque_immutable_import_revision(tmp_path):
    import_id = "vault-import:opaque:Ω-2026-11-19"
    root, db_path, inventory, attestation = _fixture(
        tmp_path, {"kind": "immutable_import", "import_id": import_id}
    )
    report = _verify(root, db_path, inventory, attestation)
    assert report.source_revision == ImmutableImportSourceRevision(import_id)

    with pytest.raises(CloudIndexVerificationError) as mismatch:
        _verify(
            root, db_path, inventory, attestation,
            expected_source_revision=ImmutableImportSourceRevision(import_id + ":different"),
        )
    assert mismatch.value.code == "source_revision_mismatch"

    with pytest.raises(CloudIndexVerificationError) as wrong_type:
        _verify(
            root, db_path, inventory, attestation,
            expected_source_revision=GitCommitSourceRevision("a" * 40),
        )
    assert wrong_type.value.code == "source_revision_mismatch"


def test_rejects_non_e1_or_mutated_expected_revision_values(tmp_path):
    root, db_path, inventory, attestation = _fixture(tmp_path)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(
            root, db_path, inventory, attestation,
            expected_source_revision={"kind": "git_commit", "commit_sha": "a" * 40},
        )
    assert error.value.code == "source_revision_invalid"


def test_rejects_nested_directory_symlink_swap_before_any_outside_file_read(tmp_path, monkeypatch):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "note.md"
    outside_file.write_text("must never be read", encoding="utf-8")
    nested = root / "nested"
    displaced = root / "nested-original"

    original_open_child = cloud_verifier._open_child_directory
    opened_outside: list[str] = []
    original_read_markdown = cloud_verifier._read_markdown_file_at

    def swap_then_open(parent_fd, name, before):
        if name == "nested" and not nested.is_symlink():
            nested.rename(displaced)
            nested.symlink_to(outside, target_is_directory=True)
        return original_open_child(parent_fd, name, before)

    def observe_markdown(parent_fd, name, relative, before, aggregate):
        if "outside" in relative or relative.endswith("nested/note.md"):
            opened_outside.append(relative)
        return original_read_markdown(parent_fd, name, relative, before, aggregate)

    monkeypatch.setattr(cloud_verifier, "_open_child_directory", swap_then_open)
    monkeypatch.setattr(cloud_verifier, "_read_markdown_file_at", observe_markdown)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "filesystem_race"
    assert opened_outside == []


def test_non_markdown_attachment_payload_is_never_opened_by_inventory_walk(tmp_path, monkeypatch):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    original_read = cloud_verifier._read_markdown_file_at
    observed: list[str] = []

    def observe_markdown(parent_fd, name, relative, before, aggregate):
        observed.append(relative)
        return original_read(parent_fd, name, relative, before, aggregate)

    monkeypatch.setattr(cloud_verifier, "_read_markdown_file_at", observe_markdown)
    report = _verify(root, db_path, inventory, attestation)
    assert report.markdown_document_count == 2
    assert observed == ["empty.MD", "nested/note.md"]


def test_attestation_and_inventory_byte_limits_accept_exact_boundary_and_reject_one_over(tmp_path, monkeypatch):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    raw_attestation = _canonical(attestation)
    monkeypatch.setattr(cloud_verifier, "MAX_ATTESTATION_BYTES", len(raw_attestation))
    _verify(root, db_path, inventory, attestation)

    monkeypatch.setattr(cloud_verifier, "MAX_ATTESTATION_BYTES", len(raw_attestation) - 1)
    with pytest.raises(CloudIndexVerificationError) as attestation_error:
        _verify(root, db_path, inventory, attestation)
    assert attestation_error.value.code == "resource_limit_exceeded"

    monkeypatch.setattr(cloud_verifier, "MAX_ATTESTATION_BYTES", len(raw_attestation))
    monkeypatch.setattr(cloud_verifier, "MAX_INVENTORY_BYTES", len(inventory))
    _verify(root, db_path, inventory, attestation)

    monkeypatch.setattr(cloud_verifier, "MAX_INVENTORY_BYTES", len(inventory) - 1)
    with pytest.raises(CloudIndexVerificationError) as inventory_error:
        _verify(root, db_path, inventory, attestation)
    assert inventory_error.value.code == "resource_limit_exceeded"


def test_parser_pairs_and_markdown_rows_enforce_exact_and_one_over_boundaries(tmp_path, monkeypatch):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    rows = len(json.loads(inventory)["documents"])
    monkeypatch.setattr(cloud_verifier, "MAX_MARKDOWN_ROWS", rows)
    monkeypatch.setattr(cloud_verifier, "MAX_PARSER_IDENTITIES", len(attestation["parser_identities"]))
    _verify(root, db_path, inventory, attestation)

    monkeypatch.setattr(cloud_verifier, "MAX_MARKDOWN_ROWS", rows - 1)
    with pytest.raises(CloudIndexVerificationError) as rows_error:
        _verify(root, db_path, inventory, attestation)
    assert rows_error.value.code == "resource_limit_exceeded"

    monkeypatch.setattr(cloud_verifier, "MAX_MARKDOWN_ROWS", rows)
    monkeypatch.setattr(
        cloud_verifier, "MAX_PARSER_IDENTITIES", len(attestation["parser_identities"]) - 1
    )
    with pytest.raises(CloudIndexVerificationError) as parsers_error:
        _verify(root, db_path, inventory, attestation)
    assert parsers_error.value.code == "resource_limit_exceeded"


def test_source_tree_entry_count_enforces_exact_and_one_over_boundary(tmp_path, monkeypatch):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    entries = 4  # nested directory, two root files, and the nested Markdown file
    monkeypatch.setattr(cloud_verifier, "MAX_SOURCE_TREE_ENTRIES", entries)
    _verify(root, db_path, inventory, attestation)

    monkeypatch.setattr(cloud_verifier, "MAX_SOURCE_TREE_ENTRIES", entries - 1)
    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "resource_limit_exceeded"


def test_markdown_document_and_aggregate_byte_limits_enforce_exact_boundary(tmp_path, monkeypatch):
    root, db_path, inventory, attestation = _fixture(tmp_path)
    sizes = [len((root / "nested" / "note.md").read_bytes()), len((root / "empty.MD").read_bytes())]
    aggregate = sum(sizes)
    monkeypatch.setattr(cloud_verifier, "MAX_MARKDOWN_DOCUMENT_BYTES", max(sizes))
    monkeypatch.setattr(cloud_verifier, "MAX_AGGREGATE_MARKDOWN_BYTES", aggregate)
    _verify(root, db_path, inventory, attestation)

    monkeypatch.setattr(cloud_verifier, "MAX_MARKDOWN_DOCUMENT_BYTES", max(sizes) - 1)
    with pytest.raises(CloudIndexVerificationError) as document_error:
        _verify(root, db_path, inventory, attestation)
    assert document_error.value.code == "resource_limit_exceeded"

    monkeypatch.setattr(cloud_verifier, "MAX_MARKDOWN_DOCUMENT_BYTES", max(sizes))
    monkeypatch.setattr(cloud_verifier, "MAX_AGGREGATE_MARKDOWN_BYTES", aggregate - 1)
    with pytest.raises(CloudIndexVerificationError) as aggregate_error:
        _verify(root, db_path, inventory, attestation)
    assert aggregate_error.value.code == "resource_limit_exceeded"


def test_relative_path_length_accepts_4096_and_rejects_one_over():
    assert cloud_verifier._safe_path("a" * 4096) == "a" * 4096
    with pytest.raises(CloudIndexVerificationError) as error:
        cloud_verifier._safe_path("a" * 4097)
    assert error.value.code == "resource_limit_exceeded"


def _refresh_database_attestation(root, db_path, attestation):
    inventory = _refresh_attestation(root, db_path, attestation)
    raw = db_path.read_bytes()
    attestation["database"]["sha256"] = _sha(raw)
    attestation["database"]["byte_size"] = len(raw)
    return inventory


def _create_second_generation(root, db_path, attestation):
    note = root / "nested" / "note.md"
    note.write_bytes("# Заголовок\r\n\r\nA revised body in a later generation.\r\n".encode("utf-8"))
    index_vault(root, db_path.parent)
    return _refresh_database_attestation(root, db_path, attestation)


def test_rejects_historical_version_with_missing_or_cross_document_parent_even_after_digest_refresh(tmp_path):
    root, db_path, _inventory_bytes, attestation = _fixture(tmp_path)
    inventory = _create_second_generation(root, db_path, attestation)
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT node_pk FROM node_versions "
            "WHERE version_no=1 AND parent_node_id IS NOT NULL "
            "AND node_pk IN (SELECT node_pk FROM node_versions GROUP BY node_pk HAVING COUNT(*) > 1) "
            "LIMIT 1"
        ).fetchone()
        assert row is not None
        connection.execute(
            "UPDATE node_versions SET parent_node_id=? WHERE node_pk=? AND version_no=1",
            ("node_" + "f" * 36, row[0]),
        )
        connection.commit()
    finally:
        connection.close()
    inventory = _refresh_database_attestation(root, db_path, attestation)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "node_reference_mismatch"


def test_rejects_historical_version_coordinate_corruption_after_digest_refresh(tmp_path):
    root, db_path, _inventory_bytes, attestation = _fixture(tmp_path)
    inventory = _create_second_generation(root, db_path, attestation)
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT node_pk FROM node_versions GROUP BY node_pk HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone()
        assert row is not None
        connection.execute(
            "UPDATE node_versions SET char_end=char_start-1 "
            "WHERE node_pk=? AND version_no=1",
            (row[0],),
        )
        connection.commit()
    finally:
        connection.close()
    inventory = _refresh_database_attestation(root, db_path, attestation)

    with pytest.raises(CloudIndexVerificationError) as error:
        _verify(root, db_path, inventory, attestation)
    assert error.value.code == "node_span_mismatch"
