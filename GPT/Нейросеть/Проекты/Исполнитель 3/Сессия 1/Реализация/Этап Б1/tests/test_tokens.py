from __future__ import annotations

from sfra_context_builder import TiktokenCounter


def test_production_token_counter_uses_configured_tiktoken_encoding():
    counter = TiktokenCounter("o200k_base")
    result = counter.count("Точный исходный фрагмент 🪄")
    metadata = counter.metadata()

    assert result > 0
    assert metadata == {
        "name": "tiktoken",
        "version": "0.14.0",
        "encoding": "o200k_base",
        "exact_for_encoding": True,
        "exact_for_client_model": False,
    }
