from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import urllib.request
from pathlib import Path


def post_issue_comment(body: str) -> str:
    api_url = os.environ["GITHUB_API_URL"].rstrip("/")
    repository = os.environ["GITHUB_REPOSITORY"]
    issue_number = os.environ["GITHUB_ISSUE_NUMBER"]
    token = os.environ["GITHUB_TOKEN"]
    url = f"{api_url}/repos/{repository}/issues/{issue_number}/comments"
    request = urllib.request.Request(
        url,
        data=json.dumps({"body": body}, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    return result.get("html_url", "comment-created")


def select_most_specific(hits: list[dict]) -> list[dict]:
    """Hide a matching ancestor when a more specific nested node also matches."""
    selected = []
    for hit in sorted(hits, key=lambda item: (
        item["source_path"],
        item["char_end"] - item["char_start"],
        item["char_start"],
    )):
        is_ancestor_of_another_hit = any(
            other["source_path"] == hit["source_path"]
            and other["node_id"] != hit["node_id"]
            and other["char_start"] >= hit["char_start"]
            and other["char_end"] <= hit["char_end"]
            and (
                other["char_start"] > hit["char_start"]
                or other["char_end"] < hit["char_end"]
            )
            for other in hits
        )
        if not is_ancestor_of_another_hit:
            selected.append(hit)
    return sorted(selected, key=lambda item: (
        item["source_path"], item["char_start"], item["char_end"]
    ))


def run_search(vault_path: Path, index_dir: Path, query: str, expected_path: str) -> str:
    # Import after the workflow installs the actual Stage-B/C implementation.
    from sfra_indexer.indexer import index_vault

    if not query or len(query) > 120 or "\n" in query or "\r" in query:
        raise ValueError("query must be a non-empty single line of at most 120 characters")
    expected = Path(expected_path)
    if expected.is_absolute() or ".." in expected.parts:
        raise ValueError("expected_path must be a safe path relative to the Vault")

    index_result = index_vault(vault_path, index_dir)
    connection = sqlite3.connect(index_result.database_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("CREATE VIRTUAL TABLE temp.sfra_fts5_probe USING fts5(value)")
        connection.execute("DROP TABLE temp.sfra_fts5_probe")

        connection.execute("DROP TABLE IF EXISTS sfra_search_fts")
        connection.execute(
            """CREATE VIRTUAL TABLE sfra_search_fts USING fts5(
                source_path UNINDEXED,
                node_id UNINDEXED,
                content_hash UNINDEXED,
                node_type UNINDEXED,
                node_status UNINDEXED,
                char_start UNINDEXED,
                char_end UNINDEXED,
                heading_path,
                raw_text,
                tokenize='unicode61 remove_diacritics 0'
            )"""
        )

        current_nodes = connection.execute(
            """SELECT d.source_path, n.node_id, n.content_hash, n.node_type,
                      n.status, n.char_start, n.char_end,
                      n.heading_path_json, n.raw_text
               FROM structural_nodes AS n
               JOIN documents AS d ON d.document_pk = n.document_pk
               WHERE d.status = 'active'
                 AND n.status IN ('active', 'ambiguous')
                 AND n.stale_generation IS NULL
                 AND n.node_id IS NOT NULL
                 AND n.content_hash IS NOT NULL"""
        ).fetchall()

        connection.executemany(
            """INSERT INTO sfra_search_fts(
                source_path, node_id, content_hash, node_type, node_status,
                char_start, char_end, heading_path, raw_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    row["source_path"],
                    row["node_id"],
                    row["content_hash"],
                    row["node_type"],
                    row["status"],
                    row["char_start"],
                    row["char_end"],
                    row["heading_path_json"] or "",
                    row["raw_text"] or "",
                )
                for row in current_nodes
            ],
        )

        # A quoted FTS5 phrase is passed as a bound parameter, never interpolated
        # into SQL. Double quotes inside a phrase are escaped per FTS5 syntax.
        phrase = '"' + query.replace('"', '""') + '"'
        matches = connection.execute(
            """SELECT source_path, node_id, content_hash, node_type, node_status,
                      char_start, char_end, heading_path, raw_text,
                      snippet(sfra_search_fts, 8, '【', '】', ' … ', 18) AS excerpt
               FROM sfra_search_fts
               WHERE sfra_search_fts MATCH ?
               ORDER BY bm25(sfra_search_fts)
               LIMIT 20""",
            (phrase,),
        ).fetchall()

        if not matches:
            raise AssertionError(f"FTS5 returned no matches for phrase: {query!r}")

        verified = []
        for row in matches:
            source_file = vault_path / row["source_path"]
            source_text = source_file.read_bytes().decode("utf-8")
            node_row = connection.execute(
                """SELECT char_start, char_end, line_start, line_end, raw_text
                   FROM structural_nodes
                   WHERE node_id = ? AND content_hash = ?""",
                (row["node_id"], row["content_hash"]),
            ).fetchone()
            if node_row is None:
                raise AssertionError(f"Search hit lost its structural node: {row['node_id']}")
            exact_slice = source_text[node_row["char_start"]:node_row["char_end"]]
            if exact_slice != node_row["raw_text"] or exact_slice != row["raw_text"]:
                raise AssertionError(f"Source slice mismatch for {row['node_id']}")
            calculated_hash = "sha256:" + hashlib.sha256(
                exact_slice.encode("utf-8")
            ).hexdigest()
            if calculated_hash != row["content_hash"]:
                raise AssertionError(f"Content hash mismatch for {row['node_id']}")
            verified.append({
                "source_path": row["source_path"],
                "node_id": row["node_id"],
                "content_hash": row["content_hash"],
                "node_type": row["node_type"],
                "node_status": row["node_status"],
                "heading_path": json.loads(row["heading_path"] or "[]"),
                "char_start": node_row["char_start"],
                "char_end": node_row["char_end"],
                "line_start": node_row["line_start"],
                "line_end": node_row["line_end"],
                "excerpt": row["excerpt"],
            })

        selected = select_most_specific(verified)
        expected_hits = [
            item for item in selected
            if item["source_path"] == expected.as_posix()
        ]
        if not expected_hits:
            found_paths = sorted({item["source_path"] for item in selected})
            raise AssertionError(
                f"Phrase found, but expected source {expected.as_posix()!r} was absent "
                f"after ancestor suppression. Returned paths: {found_paths}"
            )

        fts_rows = connection.execute(
            "SELECT COUNT(*) FROM sfra_search_fts"
        ).fetchone()[0]
        summary = {
            "documents_seen": index_result.documents_seen,
            "documents_indexed": index_result.documents_indexed,
            "documents_skipped": index_result.documents_skipped,
            "nodes_current": len(current_nodes),
            "fts_rows": fts_rows,
            "raw_matches": len(verified),
            "selected_specific_matches": len(selected),
            "suppressed_matching_ancestors": len(verified) - len(selected),
            "verified_source_slices": len(verified),
            "expected_source": expected.as_posix(),
            "expected_source_selected_matches": len(expected_hits),
            "query": query,
        }

        fence = chr(96) * 3
        tick = chr(96)
        lines = [
            "## SFRA_SEARCH_OK",
            "",
            "The real Vault was structurally indexed, loaded into temporary SQLite FTS5, searched, and the returned source slices and SHA-256 hashes were verified.",
            "",
            "### Index, search, and de-duplication metrics",
            "",
            fence + "json",
            json.dumps(summary, ensure_ascii=False, indent=2),
            fence,
            "",
            "### Selected specific search hits",
            "",
        ]
        for item in selected[:8]:
            lines.extend([
                f"- **{item['source_path']}**",
                "  - Node ID: " + tick + item["node_id"] + tick,
                "  - Content Hash: " + tick + item["content_hash"] + tick,
                "  - Node type/status: " + tick + item["node_type"] + "/" + item["node_status"] + tick,
                f"  - Source lines: {item['line_start']}-{item['line_end']}",
                "  - Heading path: " + (" → ".join(item["heading_path"]) or "(none)"),
                "  - Original-source excerpt: " + item["excerpt"],
            ])
        lines.extend([
            "",
            "Integrity checks passed: every raw FTS hit matched its exact source slice and SHA-256. Matching ancestors were suppressed where a more specific nested node also matched.",
            "The original Vault was read-only; the SQLite database and FTS5 table were created under the runner's temporary directory.",
        ])
        return "\n".join(lines)
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--index-dir", required=True, type=Path)
    args = parser.parse_args()

    author = os.environ.get("GITHUB_ISSUE_AUTHOR", "")
    title = os.environ.get("GITHUB_ISSUE_TITLE", "")
    if author != "yeatu" or not title.startswith("[SFRA-SEARCH-KERNEL]"):
        print("Refusing an issue not created by the repository owner with the expected prefix.")
        return 2

    try:
        payload = json.loads(os.environ.get("GITHUB_ISSUE_BODY", "{}"))
        if payload.get("operation") != "search_vault":
            raise ValueError("operation must be search_vault")
        report = run_search(
            args.vault,
            args.index_dir,
            str(payload.get("query", "")),
            str(payload.get("expected_path", "")),
        )
        exit_code = 0
    except Exception as exc:
        report = "\n".join([
            "## SFRA_SEARCH_FAILED",
            "",
            f"**{type(exc).__name__}:** {exc}",
            "",
            "The search test did not pass. Inspect the linked Actions run for the traceback.",
        ])
        exit_code = 1

    try:
        comment_url = post_issue_comment(report)
        print(f"Search report posted: {comment_url}")
    except Exception as exc:
        print(f"Could not post the search report: {type(exc).__name__}: {exc}")
        return 3
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
