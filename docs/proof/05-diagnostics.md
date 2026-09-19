# ProofLoop 05: request diagnostics

Acceptance: each inference request writes one local JSONL record with selected device/model, last stage, stage durations, status and a categorized failure reason. Prompts, answers, API tokens and endpoint URLs must not appear. A malformed final line must not break `/pair diagnose`.

Evidence: `test_diagnostic_journal_redacts_prompt_and_survives_partial_line`; existing MCP schema test; all 32 self-tests passed on 2026-09-19. The journal is local to the platform cache and never sent to PAIR or TypeSafe AI. A real loaded Mac model was consulted through the PAIR MCP tool during analysis; its response was truncated, illustrating why completion status matters.

Limit: LM Studio's current model inventory does not expose detailed engine memory error history. Diagnosis reports safe categories and the stage/timing observed by Bridge, not internal engine telemetry.
