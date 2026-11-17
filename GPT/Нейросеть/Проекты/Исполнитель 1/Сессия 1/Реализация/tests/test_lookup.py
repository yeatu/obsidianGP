from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path

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
    db_path = Path(result.database_path)
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
            json.dumps(
                (
                    {"old_local_key": _node_row(connection, node_id)["local_key"]}
                    if event_type in {"stale", "stale_ambiguous_candidate", "document_deleted"}
                    else {
                        "node_type": (
                            connection.execute(
                                "SELECT node_type FROM structural_nodes WHERE node_id=?",
                                (node_id,),
                            ).fetchone() or ["paragraph"]
                        )[0],
                        "reason": (
                            event_type
                            if event_type in {
                                "document_root", "unique_content_hash", "unique_heading_key",
                                "unique_sibling_heading_key", "unique_sibling_slot",
                            }
                            else None
                        ),
                    }
                ) if event_type in {
                    "document_root", "unique_content_hash", "unique_heading_key",
                    "unique_sibling_heading_key", "unique_sibling_slot", "new",
                    "ambiguous", "stale", "stale_ambiguous_candidate", "document_deleted",
                } else {}
            ),
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
    assert "🧪" in raw
    assert result.node.byte_start > result.node.char_start


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




def _prepare_deleted_document(connection, document_pk):
    rows = connection.execute(
        """SELECT node_pk, node_id, local_key FROM structural_nodes
           WHERE document_pk = ? AND status IN ('active', 'ambiguous')
             AND stale_generation IS NULL""",
        (document_pk,),
    ).fetchall()
    generation = connection.execute(
        "SELECT generation FROM documents WHERE document_pk=?",
        (document_pk,),
    ).fetchone()[0] + 1
    for item in rows:
        connection.execute(
            """UPDATE structural_nodes
               SET local_key=?, status='stale', stale_generation=?
               WHERE node_pk=?""",
            (f"__deleted__{item['node_pk']}", generation, item["node_pk"]),
        )
        connection.execute(
            """INSERT INTO node_match_events(
                document_pk, generation, new_local_key, event_type, node_id,
                candidate_node_ids_json, details_json
            ) VALUES (?, ?, NULL, 'document_deleted', ?, '[]', ?)""",
            (
                document_pk,
                generation,
                item["node_id"],
                json.dumps({"old_local_key": item["local_key"]}),
            ),
        )
    connection.execute(
        "UPDATE documents SET status='deleted', generation=? WHERE document_pk=?",
        (generation, document_pk),
    )
    return generation


def _contains_payload_key(value, key):
    if isinstance(value, dict):
        return key in value or any(
            _contains_payload_key(child, key) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_payload_key(child, key) for child in value)
    return False


def _assert_db_only_failure_without_source_read(monkeypatch, operation):
    def fail_open(*args, **kwargs):
        raise AssertionError("DB-only preflight must not open the Markdown source")

    monkeypatch.setattr("sfra_indexer.lookup._read_source_file", fail_open)
    result = operation()
    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None
    payload = result.to_dict()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["node"] is None
    assert not _contains_payload_key(payload, "raw_text")
    assert "Target paragraph." not in serialized


def test_empty_document_root_can_be_read_exactly(tmp_path):
    vault = tmp_path / "empty-vault"
    vault.mkdir()
    source_file = vault / "empty.md"
    source_file.write_bytes(b"")
    index_result = index_vault(vault, tmp_path / "empty-sidecar")
    db_path = Path(index_result.database_path)

    connection = _connect(db_path)
    root = connection.execute(
        """SELECT n.node_id, n.content_hash
           FROM structural_nodes n
           JOIN documents d ON d.document_pk=n.document_pk
           WHERE n.node_type='document' AND d.source_path='empty.md'"""
    ).fetchone()
    connection.close()

    result = get_node_by_id(db_path, root["node_id"], root["content_hash"], vault)

    assert result.status is NodeLookupStatus.OK
    assert result.node is not None
    assert result.node.raw_text == ""
    assert result.node.char_start == result.node.char_end == 0
    assert result.node.byte_start == result.node.byte_end == 0
    assert (result.node.line_start, result.node.line_end) == (1, 0)


def test_deleted_document_with_unsafe_source_path_is_db_only_integrity_error(
    tmp_path, monkeypatch
):
    vault, _, db_path, node_id, _, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    _prepare_deleted_document(connection, row["doc_pk"])
    connection.execute(
        "UPDATE documents SET source_path='../outside.md' WHERE document_pk=?",
        (row["doc_pk"],),
    )
    connection.commit()
    connection.close()

    _assert_db_only_failure_without_source_read(
        monkeypatch,
        lambda: get_node_by_id(db_path, node_id, "sha256:" + ("0" * 64), vault),
    )


def test_deleted_document_current_row_mismatch_with_latest_version_fails_preflight(
    tmp_path, monkeypatch
):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    _prepare_deleted_document(connection, row["doc_pk"])
    connection.execute(
        "UPDATE structural_nodes SET char_start=char_start+1 WHERE node_id=?",
        (node_id,),
    )
    connection.commit()
    connection.close()

    _assert_db_only_failure_without_source_read(
        monkeypatch,
        lambda: get_node_by_id(db_path, node_id, expected_hash, vault),
    )


def test_deleted_document_raw_text_hash_mismatch_fails_preflight(tmp_path, monkeypatch):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    _prepare_deleted_document(connection, row["doc_pk"])
    connection.execute(
        "UPDATE structural_nodes SET raw_text=raw_text || 'tampered' WHERE node_id=?",
        (node_id,),
    )
    connection.commit()
    connection.close()

    _assert_db_only_failure_without_source_read(
        monkeypatch,
        lambda: get_node_by_id(db_path, node_id, expected_hash, vault),
    )


def test_deleted_document_unknown_event_in_history_fails_preflight(tmp_path, monkeypatch):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    generation = _prepare_deleted_document(connection, row["doc_pk"])
    _insert_event(
        connection,
        row["doc_pk"],
        generation,
        "future_unrecognized_event",
        node_id,
    )
    connection.commit()
    connection.close()

    _assert_db_only_failure_without_source_read(
        monkeypatch,
        lambda: get_node_by_id(db_path, node_id, expected_hash, vault),
    )


@pytest.mark.parametrize(
    ("replacement", "event_type"),
    [
        ({"node_type": "paragraph"}, "new"),
        ({"node_type": "paragraph", "reason": "wrong_reason"}, "document_root"),
    ],
)
def test_event_details_json_is_validated_by_event_type(
    tmp_path, replacement, event_type
):
    source = "# Header\n\nTarget paragraph.\n"
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path, source)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    if event_type == "document_root":
        # The first indexing generation uses 'new' for each node. A synthetic
        # reused-event row exercises the exact reason field required by storage.py.
        _insert_event(
            connection,
            row["doc_pk"],
            1,
            event_type,
            node_id,
            local_key="n999999",
        )
    else:
        connection.execute(
            """UPDATE node_match_events SET details_json=?
               WHERE event_pk=(
                   SELECT event_pk FROM node_match_events
                   WHERE document_pk=? AND node_id=? AND event_type='new'
                   ORDER BY event_pk LIMIT 1
               )""",
            (json.dumps(replacement), row["doc_pk"], node_id),
        )
    if event_type == "document_root":
        connection.execute(
            """UPDATE node_match_events SET details_json=?
               WHERE event_pk=(SELECT MAX(event_pk) FROM node_match_events
                               WHERE document_pk=? AND node_id=?)""",
            (json.dumps(replacement), row["doc_pk"], node_id),
        )
    connection.commit()
    connection.close()

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None
    assert "raw_text" not in json.dumps(result.to_dict())


def test_deleted_document_event_payload_requires_old_local_key(tmp_path):
    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    connection = _connect(db_path)
    row = _node_row(connection, node_id)
    generation = _prepare_deleted_document(connection, row["doc_pk"])
    connection.execute(
        """UPDATE node_match_events SET details_json='{}'
           WHERE document_pk=? AND generation=? AND event_type='document_deleted'
             AND node_id=?""",
        (row["doc_pk"], generation, node_id),
    )
    connection.commit()
    connection.close()

    result = get_node_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.INTEGRITY_ERROR
    assert result.node is None
    assert "raw_text" not in json.dumps(result.to_dict())


def test_get_parent_by_id_returns_verified_parent_and_handles_root(tmp_path):
    from sfra_indexer import get_parent_by_id

    vault, _, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path)
    child_result = get_parent_by_id(db_path, node_id, expected_hash, vault)

    assert child_result.status is NodeLookupStatus.OK
    assert child_result.node is not None
    assert child_result.parent is not None
    assert child_result.parent.node_type == "heading"
    assert child_result.parent.raw_text.startswith("# Header")

    connection = _connect(db_path)
    root = connection.execute(
        "SELECT node_id, content_hash FROM structural_nodes WHERE node_type='document'"
    ).fetchone()
    connection.close()
    root_result = get_parent_by_id(
        db_path, root["node_id"], root["content_hash"], vault
    )
    assert root_result.status is NodeLookupStatus.OK
    assert root_result.node is not None
    assert root_result.parent is None


def test_get_neighbors_by_id_returns_immediate_source_ordered_siblings(tmp_path):
    from sfra_indexer import get_neighbors_by_id

    source = "# Header\n\nFirst paragraph.\n\nMiddle paragraph.\n\nLast paragraph.\n"
    vault, _, db_path, _, _, _ = _indexed_note(tmp_path, source)
    connection = _connect(db_path)
    rows = connection.execute(
        """SELECT node_id, content_hash, raw_text FROM structural_nodes
           WHERE node_type='paragraph' AND status='active'
           ORDER BY char_start"""
    ).fetchall()
    connection.close()

    result = get_neighbors_by_id(
        db_path, rows[1]["node_id"], rows[1]["content_hash"], vault
    )

    assert result.status is NodeLookupStatus.OK
    assert result.node is not None
    assert result.previous is not None
    assert result.next is not None
    assert result.previous.raw_text == rows[0]["raw_text"]
    assert result.next.raw_text == rows[2]["raw_text"]


def test_get_neighbors_by_id_does_not_skip_ambiguous_immediate_sibling(tmp_path):
    from sfra_indexer import get_neighbors_by_id

    source = "# Header\n\nFirst paragraph.\n\nMiddle paragraph.\n\nLast paragraph.\n"
    vault, _, db_path, _, _, _ = _indexed_note(tmp_path, source)
    connection = _connect(db_path)
    rows = connection.execute(
        """SELECT node_id, content_hash, local_key, document_pk, node_type
           FROM structural_nodes WHERE node_type='paragraph' ORDER BY char_start"""
    ).fetchall()
    connection.execute(
        "UPDATE structural_nodes SET status='ambiguous' WHERE node_id=?",
        (rows[0]["node_id"],),
    )
    _insert_event(
        connection,
        rows[0]["document_pk"],
        1,
        "ambiguous",
        rows[0]["node_id"],
        local_key=rows[0]["local_key"],
        candidates=["node_" + str(uuid.uuid4())],
    )
    connection.commit()
    connection.close()

    result = get_neighbors_by_id(
        db_path, rows[1]["node_id"], rows[1]["content_hash"], vault
    )

    assert result.status is NodeLookupStatus.AMBIGUOUS
    assert result.node is None
    assert result.previous is None
    assert result.next is None


def test_get_document_by_id_returns_exact_complete_markdown(tmp_path):
    from sfra_indexer import get_document_by_id

    source = "# Заголовок\n\nПолный исходный текст 🧪.\r\n"
    vault, note, db_path, node_id, expected_hash, _ = _indexed_note(tmp_path, source)
    result = get_document_by_id(db_path, node_id, expected_hash, vault)

    assert result.status is NodeLookupStatus.OK
    assert result.anchor is not None
    assert result.document is not None
    assert result.document.raw_text == source
    assert result.document.raw_text.encode("utf-8") == note.read_bytes()
    assert result.document.source_sha256 == "sha256:" + hashlib.sha256(
        note.read_bytes()
    ).hexdigest()


def test_related_read_modes_propagate_anchor_stale_hash_without_partial_content(tmp_path):
    from sfra_indexer import (
        get_document_by_id,
        get_neighbors_by_id,
        get_parent_by_id,
    )

    vault, _, db_path, node_id, _, _ = _indexed_note(tmp_path)
    wrong_hash = "sha256:" + ("0" * 64)
    operations = (
        get_parent_by_id,
        get_neighbors_by_id,
        get_document_by_id,
    )
    for operation in operations:
        result = operation(db_path, node_id, wrong_hash, vault)
        assert result.status is NodeLookupStatus.STALE_SOURCE
        assert result.to_dict()["node"] is None if "node" in result.to_dict() else result.to_dict()["anchor"] is None


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
