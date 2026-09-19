# ProofLoop: smart routing and integrations

Date: 2026-09-19. Scope: local development checkout; no release or deployment.

| ID | Acceptance condition | Evidence | Result |
| --- | --- | --- | --- |
| PAIR-01 | Missing model ID never starts a download. | `test_selector_prefers_loaded_installed_chat`, `test_no_download_for_missing_model` | PASS |
| PAIR-02 | Existing loaded instance is reused and preserved. | `test_smart_ask_preserves_existing_instance`; live Mac request returned `cleanup=existing_instance_preserved`, `finish_reason=stop`, answer `OK`. | PASS |
| PAIR-03 | Freshly loaded instance is identified by the load response and unloaded only after success. | `test_smart_ask_loads_and_unloads_only_owned_instance`; API sequence load → ask → unload. | PASS in mock; real cold-load still needed |
| PAIR-04 | Timeout never triggers blind retry or unload. | `test_timeout_retains_new_instance_for_inspection`, `test_timeout_no_retry` | PASS |
| PAIR-05 | Comparison preserves both targets, including partial failure. | `test_compare_preserves_both_provenances_and_one_failure` | PASS in mock; two-device live run blocked by offline node |
| PAIR-06 | Diagnostics omit model names, instance IDs and prompt text. | `test_diagnostics_omits_private_router_url_and_model_names`; live diagnostics found one online Mac device and one offline node. | PASS |
| PAIR-07 | Jev does not send state without explicit opt-in and validates typed answers. | `test_external_send_requires_explicit_opt_in`, `test_choice_response_is_validated`, `test_score_response_is_validated`, `test_score_rejects_wrong_legend` | PASS in mock; live Jev key unavailable |
| PAIR-08 | OMP has a documented MCP installation path and native command/skill. | `.omp/commands/pair.md`, `.omp/skills/pair/SKILL.md`, `docs/OMP.md`; OMP 18.1.10 installed locally; isolated headless launch reached model setup and stopped because no model/API key was configured. | CONFIG READY; end-to-end OMP session not yet tested |
| PAIR-09 | Explicit download requires a reviewed, one-use plan and exact repeated model ID. | `test_download_requires_repeated_exact_model`, `test_download_plan_is_one_use_and_exposes_review_fields`, `test_download_plan_rejects_untrusted_url` | PASS in mock; no weights downloaded |

Validation command: `UV_CACHE_DIR=/private/tmp/pair-uv-cache uv run --offline --locked --script ./scripts/server.py --self-test` from `plugins/pair-bridge`. Result: 31 tests passed, including MCP tool discovery.

Analysis tools: Graphify rebuilt a temporary code graph (241 nodes, 255 edges); zvec-grep refreshed an index of 56 scanned project files and returned source-linked results for model ownership; EchoVault v0.5.0 retrieved the lifecycle decision and saved the Jev/download-plan decision in a temporary local vault (FTS worked; vector embedding was unavailable in this sandbox). The initial PAIR model consultation had no final text; the live smart-ask smoke test used a larger output budget and returned `OK` without changing loaded state.

Remaining proof: live cold-load/unload; two-model comparison; Jev API call with a user-provided key and non-sensitive state; OMP MCP connection in a separate project; independent download estimate, destination and free-space validation; device-specific queue/resource limits. Do not claim these are complete.
