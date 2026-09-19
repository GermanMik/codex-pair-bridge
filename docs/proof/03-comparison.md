# ProofLoop 03: two-model comparison

Acceptance: the same bounded prompt goes sequentially to two explicit installed model/device targets. Both answers retain provenance, timing and usage. Textual agreements and disputes are separated, but no statement is called true until Codex checks the source files.

Evidence: `test_compare_preserves_both_provenances_and_one_failure` and `test_compare_marks_disagreement_unverified`; full self-test suite passed. The PAIR inventory currently exposes only one installed chat LLM on one online device, so a live two-model comparison could not be run without installing additional weights. The tool reports `verification_status=requires_codex_source_review`; the PAIR and OMP instructions require file review.
