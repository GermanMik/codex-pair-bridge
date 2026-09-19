# ProofLoop 02: task-profile model selection

Acceptance: a `/pair` code, fast, long-context or analysis task chooses only an installed online chat model; explicit model/device overrides are honored. The response states the selection profile and reason. No missing model ID is guessed or downloaded.

Evidence: `test_profile_selection_and_explicit_override` covers the four profiles, explicit override and missing key. The full MCP self-test suite passed. Live hardware currently advertises only one installed chat LLM on an online device, so cross-model ranking is verified deterministically in tests rather than a live multi-model run.
