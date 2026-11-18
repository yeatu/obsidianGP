# Coverage matrix — synthetic gold corpus v1

| Category | Cases | Count | Coverage |
|---|---|---:|---|
| Large documents / headings | gq-001, gq-011, gq-040 | 3 | Multi-section and critical constraints |
| No headings / nested lists | gq-002, gq-003, gq-041 | 3 | Empty heading_path, coordinates, nested list |
| Rules / exceptions | gq-004, gq-005 | 2 | Preservation, required_with, atomic delivery |
| Entities / aliases / ambiguity | gq-006–gq-008 | 3 | Canonical names, alias variants, short-code distractor |
| Exact numbers / multi-part | gq-009, gq-010 | 2 | Numeric exactness and combined evidence |
| Multi-document / parallel sources | gq-017, gq-018, gq-033 | 3 | Distinct paths and similar text |
| Multi-facet | gq-012, gq-033, gq-040 | 3 | Per-facet required IDs |
| Parent / dependencies / cycles | gq-013–gq-016 | 4 | Parent context, recursive closure, unresolved dependency, SCC |
| Empty / negative / noise | gq-019–gq-021 | 3 | Empty spans, empty query, punctuation noise |
| Search completeness | gq-022, gq-042 | 2 | Incomplete batch; no false absence claim |
| Budget / atomicity | gq-023–gq-025 | 3 | Atomic groups, defer, E1 budget_exceeded |
| Source states | gq-026–gq-029 | 4 | Stale, deleted, ambiguous, not_found |
| Read scopes | gq-030–gq-032 | 3 | Document, neighbors, parent |
| Known / version / integrity | gq-034–gq-036 | 3 | Known, Version Changes, conflicting hashes |
| Trust / uncertainty / provenance | gq-037–gq-039 | 3 | Untrusted source, author uncertainty, exact provenance |
| **Total** | **gq-001–gq-042** | **42** | **Issue #41 classes represented** |

## Notes
- 32 synthetic Markdown documents and 69 annotated nodes.
- E1 budget_exceeded is not a Context Pack status; it is tested separately in expected_read_source.
- empty_root uses empty raw_text, line_start=1, line_end=0.
- source_state is a fixture control, not a production API field.
- The corpus defines expectations; it does not claim the runtime already meets them.
