from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

import pytest

from sfra_indexer import (
    NodeLookupStatus,
    get_node_by_id,
    index_vault,
)


def _indexed_note(tmp_path, source: str = "# Header\n\nTarget paragraph.\n"):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "note.md"
    note.write_bytes(source.encode("utf-8"))
    before = note.read_bytes()

    result = index_vault(vault, tmp_path / "sidecar")
    db_path = result.database_path
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """SELECT n.*, d.source_path, d.source_sha256, d.source_size_bytes,
                  d.status AS document_status, d.generation AS document_generation
           FROM structural_nodes n
           JOIN documents d ON d.document_pk = n.document_pk
           WHERE n.node_type = 'paragraph'
           ORDER BY n.node_pk LIMIT 1"""
    ).fetchone()
    assert row is not None
    node_id = row["node_id"]
    expected_hash = row["content_hash"]
    connection.close()
    return vault, note, db_path, node_id, expected_hash, before


def _connect(db_path):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _insert_event(connection, document_pk, generation, event_type, node_id,
                  *, local_key=None, candidates=None):
    connection.execute(
        """INSERT INTO node_match_events(
            document_pk, generation, new_local_key, event_type, node_id,
            candidate_node_ids_json, details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            document_pk,
            generation,
            local_key,
            event_type,
            node_id,
            json.dumps(candidates or []),
            json.dumps({"reason": "lookup test"}),
        ),
    )


def _node_row(connection, node_id):
    return connection.execute(
        """SELECT n.*, d.document_pk AS doc_pk
           FROM structural_nodes n
           JOIN documents d ON d.document_pk = n.document_pk
           WHERE n.node_id = ?""",
        (node_id,),
    ).fetchone()


def test_reads_exact_active_source_slice_and_returns_address_metadata(tmp_path):
    vault, note, db_path, node_id, expected_hash, original = _indexed_note(tmp_path)
    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.OK
    assert result.node is not None
    assert result.node.node_id == node_id
    assert result.node.raw_text == "Target paragraph.\n"
    assert result.node.raw_text == original[
        result.node.char_start:result.node.char_end
    ].decode("utf-8")
    assert result.node.content_hash == expected_hash
    assert result.node.source_path == "note.md"
    assert result.node.line_start == 3
    assert result.node.line_end == 3
    assert result.node.source_sha256 == "sha256:" + hashlib.sha256(original).hexdigest()
    assert result.to_dict()["node"]["raw_text"] == result.node.raw_text


def test_wrong_expected_hash_is_stale_and_does_not_return_node(tmp_path):
    vault, _, db_path, node_id, _, _ = _indexed_note(tmp_path)
    wrong_hash = "sha256:" + ("0" * 64)

    result = get_node_by_id(db_path, node_id, wrong_hash, vault)

    assert result.status is NodeLookupStatus.STALE_SOURCE
    assert result.node is None
    assert result.to_dict()["node"] is None
    assert "raw_text" not in json.dumps(result.to_dict())


def test_missing_node_id_is_not_found(tmp_path):
    vault, _, db_path, _, _, _ = _indexed_note(tmp_path)
    missing_id = "node_" + str(uuid.uuid4())

    result = get_node_by_id(db_path, missing_id, "sha256:" + ("0" * 64), vault)

    assert result.status is NodeLookupStatus.NOT_FOUND
    assert result.node is None


@pytest.mark.parametrize(
    ("node_id", "expected_hash"),
    [
        ("bad-id", "sha256:" + ("0" * 64)),
        ("node_" + str(uuid.uuid4()), "not-a-hash"),
    ],
)
def test_invalid_node_id_or_hash_is_rejected(tmp_path, node_id, expected_hash):
    vault, _, db_path, _, _, _ = _indexed_note(tmp_path)

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INVALID_REQUEST
    assert result.node is None


def test_ambiguous_node_is_rejected_before_opening_source(tmp_path, monkeypatch):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    candidate_id = "node_" + str(uuid.uuid4())
    connection.execute(
        "UPDATE structural_nodes SET status='ambiguous' WHERE node_id=?",
        (node_id,),
    )
    _insert_event(
        connection,
        row["doc_pk"],
        1,
        "ambiguous",
        node_id,
        local_key=row["local_key"],
        candidates=[candidate_id],
    )
    connection.commit()
    connection.close()

    def fail_open(*args, **kwargs):
        raise AssertionError("source must not be opened for ambiguous nodes")

    monkeypatch.setattr("sfra_indexer.lookup._read_source_file", fail_open)
    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.AMBIGUOUS
    assert result.node is None


def test_stale_node_is_reported_as_deleted_address(tmp_path, monkeypatch):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    connection.execute(
        """UPDATE structural_nodes
           SET status='stale', stale_generation=2
           WHERE node_id=?""",
        (node_id,),
    )
    connection.execute(
        "UPDATE documents SET generation=2 WHERE document_pk=?",
        (row["doc_pk"],),
    )
    _insert_event(connection, row["doc_pk"], 2, "stale", node_id)
    connection.commit()
    connection.close()

    def fail_open(*args, **kwargs):
        raise AssertionError("source must not be opened for a deleted node")

    monkeypatch.setattr("sfra_indexer.lookup._read_source_file", fail_open)
    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.DELETED
    assert result.node is None


def test_deleted_document_is_reported_without_opening_markdown(tmp_path, monkeypatch):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    connection.execute(
        "UPDATE documents SET status='deleted', generation=2 WHERE document_pk=?",
        (row["doc_pk"],),
    )
    connection.execute(
        """UPDATE structural_nodes
           SET status='stale', stale_generation=2
           WHERE document_pk=? AND stale_generation IS NULL""",
        (row["doc_pk"],),
    )
    _insert_event(connection, row["doc_pk"], 2, "document_deleted", node_id)
    connection.commit()
    connection.close()

    def fail_open(*args, **kwargs):
        raise AssertionError("source must not be opened for a deleted document")

    monkeypatch.setattr("sfra_indexer.lookup._read_source_file", fail_open)
    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.DELETED
    assert result.node is None


def test_changed_target_fragment_is_rejected_as_stale_source(tmp_path):
    vault, note, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    note.write_text("# Header\n\nChanged paragraph.\n", encoding="utf-8")

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.STALE_SOURCE
    assert result.node is None


def test_change_to_another_part_of_document_invalidates_old_index(tmp_path):
    source = "# Header\n\nTarget paragraph.\n\nOther paragraph.\n"
    vault, note, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path, source)
    note.write_text(
        "# Header\n\nTarget paragraph.\n\nOther paragraph was edited.\n",
        encoding="utf-8",
    )

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.STALE_SOURCE
    assert result.node is None


@pytest.mark.parametrize(
    "source",
    [
        "# Раздел\n\nПеред 🧪 целью.\n\nСтрока с кириллицей.\n",
        "# Раздел\r\n\r\nПеред 🧪 целью.\r\n\r\nСтрока с кириллицей.\r\n",
    ],
)
def test_unicode_emoji_and_line_endings_keep_char_and_byte_offsets(tmp_path, source):
    vault, _, db_path, node_id, expected_hash, original = _indexed_note(tmp_path, source)
    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.OK
    assert result.node is not None
    raw = result.node.raw_text
    encoded = original
    assert encoded[
        result.node.byte_start:result.node.byte_end
    ].decode("utf-8") == raw
    assert raw == source[result.node.char_start:result.node.char_end]
    assert "🧪" in source[:result.node.char_start]


@pytest.mark.parametrize(
    ("column", "delta"),
    [
        ("char_start", 1),
        ("byte_start", 1),
        ("line_start", 1),
    ],
)
def test_invalid_source_coordinates_are_integrity_errors(tmp_path, column, delta):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    connection.execute(
        f"UPDATE structural_nodes SET {column}={column}+? WHERE node_id=?",
        (delta, node_id),
    )
    connection.execute(
        f"UPDATE node_versions SET {column}={column}+? WHERE node_pk=?",
        (delta, row["node_pk"]),
    )
    connection.commit()
    connection.close()

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None


def test_missing_active_source_file_is_stale_not_silently_replaced(tmp_path):
    vault, note, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    note.unlink()

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.STALE_SOURCE
    assert result.node is None


def test_path_escape_in_database_is_integrity_error(tmp_path):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    connection.execute(
        "UPDATE documents SET source_path='../outside.md' WHERE document_pk=?",
        (row["doc_pk"],),
    )
    connection.commit()
    connection.close()

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None


def test_symlink_source_is_rejected(tmp_path):
    vault, note, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("# Header\n\nTarget paragraph.\n", encoding="utf-8")
    note.unlink()
    note.symlink_to(outside)

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None


def test_tampered_sqlite_raw_text_is_integrity_error(tmp_path):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    connection.execute(
        "UPDATE structural_nodes SET raw_text=raw_text || 'tampered' WHERE node_id=?",
        (node_id,),
    )
    connection.commit()
    connection.close()

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None


def test_unknown_match_event_is_integrity_error(tmp_path):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    _insert_event(connection, row["doc_pk"], 1, "future_unknown_event", node_id)
    connection.commit()
    connection.close()

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None


def test_read_only_api_does_not_change_sqlite_or_source_vault(tmp_path):
    vault, note, db_path, node_id, expected_hash, original_source = _indexed_note(tmp_path)
    original_db = open(db_path, "rb").read()
    original_source_hash = hashlib.sha256(note.read_bytes()).hexdigest()
    original_db_hash = hashlib.sha256(original_db).hexdigest()
    existing_sidecars = sorted(
        item.name for item in db_path.parent.iterdir()
    )

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.OK
    assert hashlib.sha256(open(db_path, "rb").read()).hexdigest() == original_db_hash
    assert hashlib.sha256(note.read_bytes()).hexdigest() == original_source_hash
    assert note.read_bytes() == original_source
    assert sorted(item.name for item in db_path.parent.iterdir()) == existing_sidecars


def test_all_failed_result_shapes_have_no_node_or_source_text(tmp_path):
    vault, note, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    note.write_text("source changed\n", encoding="utf-8")
    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    payload = result.to_dict()
    assert result.status is NodeLookupStatus.STALE_SOURCE
    assert result.node is None
    assert payload["node"] is None
    assert "raw_text" not in json.dumps(payload)
    assert "Target paragraph" not in json.dumps(payload)


def test_missing_database_is_a_typed_invalid_request(tmp_path):
    vault, _, _, node_id, expected_hash, _ = _indexed_note(tmp_path)
    result = get_node_by_id(tmp_path / "missing.sqlite3", node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INVALID_REQUEST
    assert result.node is None
    assert result.to_dict()["node"] is None


def test_source_path_replacement_during_read_fails_closed(tmp_path, monkeypatch):
    vault, note, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    outside = tmp_path / "replacement.md"
    outside.write_text("# Header\n\nReplacement paragraph.\n", encoding="utf-8")

    import sfra_indexer.lookup as lookup_module

    original_open = lookup_module._open_beneath
    calls = 0

    def replace_before_second_open(root_fd, components):
        nonlocal calls
        calls += 1
        if calls == 2:
            note.unlink()
            note.symlink_to(outside)
        return original_open(root_fd, components)

    monkeypatch.setattr(lookup_module, "_open_beneath", replace_before_second_open)
    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None
