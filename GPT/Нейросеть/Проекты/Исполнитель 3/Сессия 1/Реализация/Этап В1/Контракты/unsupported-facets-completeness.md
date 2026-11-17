# Unsupported E2 facets and search completeness

The current E2 search contract has no facet parameter and exposes no explicit facet-match signal. Therefore a non-empty `SearchRequest.facets` is **not evaluated** by E2.

E3 must:
- emit `facet_match_signal_unavailable` with warning severity and `evaluation: not_evaluated`;
- set `SearchBatch.complete = false`, even when E2 returns ordinary lexical candidates;
- let B1 Coverage preserve `not_found_in_retrieval` with the existing incomplete-search diagnostic note.

E3 must not infer a facet match from query text, E2 excerpts, or unrelated metadata. This does not add facet retrieval to E2, change normal no-facet requests, or modify the existing budget policy.
