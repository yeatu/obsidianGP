from __future__ import annotations

from sfra_context_builder.integrity import content_hash, matches_content_hash


def test_sha256_uses_exact_utf8_without_newline_normalization():
    lf = "строка\n"
    crlf = "строка\r\n"
    assert content_hash(lf) != content_hash(crlf)
    assert content_hash("Кириллица 🪄") == "sha256:" + __import__("hashlib").sha256(
        "Кириллица 🪄".encode("utf-8")
    ).hexdigest()


def test_hash_comparison_accepts_hex_case_but_not_text_changes():
    original = "é\r\nтекст"
    expected = content_hash(original)
    assert matches_content_hash(original, expected.upper().replace("SHA256:", "sha256:"))
    assert not matches_content_hash(original + " ", expected)
