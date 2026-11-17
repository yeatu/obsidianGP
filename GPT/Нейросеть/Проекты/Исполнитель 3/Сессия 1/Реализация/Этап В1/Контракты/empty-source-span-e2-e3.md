# E2 → E3: empty SourceSpan contract

E3 accepts exactly one empty-span representation from E2:

- `raw_text == ""`;
- `line_start` is a positive, non-boolean integer;
- `line_end` is a non-negative, non-boolean integer;
- `line_end == line_start - 1`.

Examples:
- empty document root: `line_start=1, line_end=0`;
- empty non-root node beginning at line 4: `line_start=4, line_end=3`.

E3 does not create a synthetic line or placeholder text. It passes the exact locator to E1, then requires E1 to echo the same line coordinates and return source-derived empty text whose UTF-8 SHA-256 matches the requested content hash.

Every other inverted range is rejected as `invalid_e2_response`. An empty `raw_text` paired with an ordinary inclusive range is also rejected. Missing, malformed, boolean, negative, or non-integer coordinates remain invalid.

This contract changes only E3 response validation; it does not alter E2 ranking, source reads, SnapshotRef semantics, or production workflows.
