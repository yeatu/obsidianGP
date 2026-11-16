from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def gp_root(repository_root: Path) -> Path:
    root = repository_root / "ГП"
    assert root.is_dir(), f"Индексируемая директория не найдена: {root}"
    return root.resolve()


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    return (Path(__file__).parent / "fixtures").resolve()


@pytest.fixture(scope="session")
def indexer_api():
    module_name = os.getenv("SFRA_INDEXER_MODULE", "sfra_indexer")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name or module_name.startswith(f"{exc.name}."):
            pytest.skip(
                f"Модуль индексатора {module_name!r} ещё не установлен; "
                "автономные тесты корпуса продолжают выполняться."
            )
        raise

    required = ("scan_vault", "parse_document", "export_index")
    missing = [name for name in required if not callable(getattr(module, name, None))]
    assert not missing, (
        f"В модуле {module_name!r} отсутствуют публичные функции: {', '.join(missing)}. "
        "Ожидаемый контракт: scan_vault(root_path), "
        "parse_document(path, root_path), export_index(result, output_path)."
    )
    return module


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: invokes the actual SFRA indexer implementation",
    )
