from __future__ import annotations

from pathlib import Path
import re

import pytest

from tests.sfra_indexer.adapter import (
    AdapterNotConfigured,
    NodeView,
    iter_document_paths,
    iter_nodes,
)
from tests.sfra_indexer.test_fixtures import assert_source_integrity, read_source


LIVE_DOCUMENTS = (
    "фракции/Рэддл.md",
    "персонажи/ученики/Иное/Перси Уизли.md",
    "персонажи/ученики/Молодая кровь/Генрих Фауст.md",
    "принципы написания/принципы.md",
    "иное/Демография.md",
    "разобрать/Демография.md",
    "персонажи/преподаватели/Преподаватели.md",
)


def _nodes(result) -> list[NodeView]:
    try:
        return list(iter_nodes(result))
    except AdapterNotConfigured as exc:
        pytest.skip(str(exc))


def _paths(result, gp_root: Path) -> list[Path]:
    try:
        raw_paths = list(iter_document_paths(result, gp_root))
    except AdapterNotConfigured as exc:
        pytest.skip(str(exc))
    resolved = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = gp_root / path
        resolved.append(path.resolve())
    return resolved


def test_requested_live_documents_exist_and_are_distinct(gp_root: Path) -> None:
    resolved = [(gp_root / relative).resolve() for relative in LIVE_DOCUMENTS]
    assert all(path.is_file() for path in resolved)
    assert len(resolved) == len(set(resolved))
    assert resolved[4].name == resolved[5].name == "Демография.md"
    assert resolved[4].parent != resolved[5].parent


def test_live_document_profiles_match_current_vault_markup(gp_root: Path) -> None:
    sources = {
        relative: read_source(gp_root / relative)
        for relative in LIVE_DOCUMENTS
    }

    riddle = sources["фракции/Рэддл.md"]
    assert not re.search(r"^#{1,6}\s", riddle, re.M)
    assert re.search(r"^\t{2,}[-*+]\s", riddle, re.M)

    percy = sources["персонажи/ученики/Иное/Перси Уизли.md"]
    assert re.search(r"^>\s*\[!NOTE\]", percy, re.M)
    assert re.search(r"^>\s*\t", percy, re.M)

    henry = sources["персонажи/ученики/Молодая кровь/Генрих Фауст.md"]
    assert re.search(r"^#{1,3}\s", henry, re.M)
    assert len(re.findall(r"^#{1,3}\s", henry, re.M)) >= 10

    principles = sources["принципы написания/принципы.md"]
    assert re.search(r"^\t{2,}[-*+]\s", principles, re.M)
    assert not re.search(r"^#{1,6}\s", principles, re.M)

    short_demography = sources["иное/Демография.md"]
    assert "Соотношение магов к магглам" in short_demography
    assert not re.search(r"^#{1,6}\s", short_demography, re.M)

    draft_demography = sources["разобрать/Демография.md"]
    assert re.search(r"^\s*\|.*\|\s*$", draft_demography, re.M)
    assert "\u00a0" in draft_demography

    teachers = sources["персонажи/преподаватели/Преподаватели.md"]
    assert len(re.findall(r"\[[^\]]+\]\(https?://[^)]+\)", teachers)) >= 20
    assert "\u00a0" in teachers
    assert re.search(r"\n(?:[ \t]*\n){2,}", teachers)


@pytest.mark.integration
def test_scan_vault_is_confined_to_gp_and_finds_all_requested_documents(
    indexer_api, gp_root: Path
) -> None:
    result = indexer_api.scan_vault(str(gp_root))
    paths = _paths(result, gp_root)

    for path in paths:
        try:
            path.relative_to(gp_root.resolve())
        except ValueError:
            pytest.fail(f"Сканер вернул путь вне ГП/: {path}")
        assert path.suffix.lower() == ".md"

    expected = {(gp_root / relative).resolve() for relative in LIVE_DOCUMENTS}
    assert expected <= set(paths), "Сканер пропустил один или несколько контрольных документов"


@pytest.mark.integration
@pytest.mark.parametrize("relative_path", LIVE_DOCUMENTS)
def test_parse_real_vault_document_is_lossless(
    indexer_api, gp_root: Path, relative_path: str
) -> None:
    path = (gp_root / relative_path).resolve()
    source = read_source(path)
    result = indexer_api.parse_document(str(path), str(gp_root))
    nodes = _nodes(result)
    assert_source_integrity(source, nodes)


@pytest.mark.integration
def test_export_index_writes_to_requested_path(
    indexer_api, gp_root: Path, tmp_path: Path
) -> None:
    result = indexer_api.scan_vault(str(gp_root))
    output_path = tmp_path / "sfra-index-export.bin"
    indexer_api.export_index(result, str(output_path))
    assert output_path.exists(), "export_index() не создал результат по output_path"
    if output_path.is_file():
        assert output_path.stat().st_size > 0
    else:
        assert any(output_path.iterdir()), "export_index() создал пустой каталог"
