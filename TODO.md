# PAIR Bridge — TODO

Status: implementation in progress. Checked items have local code and tests; unchecked items still need the stated verification or behavior. Current validation: 55 self-tests passed.

## 1. Connect other agents and decision models

- [ ] **Oh My Pi (OMP, https://omp.sh/):** MCP config, native `/pair` command and skill are implemented and documented in `docs/OMP.md`. Headless smoke test is pending: the isolated OMP profile had no model/API key, so command discovery could not be confirmed end to end.
- [ ] **Jev by TypeSafe AI (https://typesafe.ai/):** optional explicit Choice and Score adapters implemented against the documented API, with offline tests and no implicit routing. Live credential-backed verification remains.

## 2. Smart `/pair ask`

- [x] Refresh live inventory and PAIR routing catalog; expose current check time/status, installed/loaded state and last request outcome, and recheck type/context under the device lock before inference.
- [x] Select an **already installed** chat model using task profile, reachability, context capacity, fresh device RAM/VRAM samples and recent local benchmark metrics when available. Unknown capacity remains explicit; ranking across devices still needs representative live benchmarks.
- [x] Reuse a suitable loaded instance, or load an installed model when needed. Record the exact instance ID and whether this task created it.
- [x] Send a bounded request, report model/device, timing, completion status and any truncation, and reject an empty answer; Codex still must verify factual claims.
- [ ] Unload only an instance created for this task, and only when no other active request depends on it. The bridge serializes per device and preserves pre-existing instances; external LM Studio clients are not visible to its lock. On timeout it leaves the instance loaded for inspection; automatic state inspection/recovery remains.
- [x] Handle no suitable model, failed load, device loss and cancellation with explicit results; never silently switch devices or models. `pair_job_cancel` stops its HTTP stream, while cancellation of LM Studio's internal generation cannot be guaranteed.

## 3. Compare and diagnose

- [x] Compare answers from two explicitly selected installed models sequentially. Each result retains provenance and usage/timing; Codex must verify disputed claims against sources.
- [x] Add local per-request diagnostics for endpoint reachability, inventory/load stages, queue/load/inference timings, sanitized timeout and empty-answer reasons. Detailed engine-memory telemetry is limited by the available LM Studio API.
- [x] Add reproducible tests for model selection, empty router catalog, missing model, simultaneous use, timeout, cleanup, memory preflight, download review, cancellation and MCP discovery; 55 self-tests pass.

## 4. Resource management and optional downloads

- [x] Add per-device 30-second queues, configurable memory-estimate budgets, live queue/preflight/load/inference stage records, load time and observed engine evictions. Exact free RAM/VRAM and streamed load percentage are not exposed by the synchronous LM Studio load endpoint.
- [x] Replace the weight-size gate with a context-aware `lms load --estimate-only` preflight for cold loads; include existing instances at their actual contexts, apply 10% headroom to configured memory budgets, expose read-only `pair_memory_plan`, and mark missing estimates unknown. Alfred live check returned Qwen 27B at 8,192 plus Ornith at its loaded 65,536 context. No weights were loaded. [LM Studio CLI](https://lmstudio.ai/docs/cli/local-models/load), [model inventory](https://lmstudio.ai/docs/developer/rest/list).
- [ ] Calibrate CLI estimates against observed usage across model/context/GPU-offload combinations. Fresh RAM/VRAM samples are now available on configured devices and block clearly oversized cold loads; `max_loaded_bytes` remains a separate user policy.
- [x] Keep downloads a **separate explicit action**, never part of ask. `pair_download_plan` now checks public Hugging Face metadata for one unambiguous GGUF file and local destination free space with 10% headroom; catalog IDs and ambiguous/sharded files retain a caller estimate with uncertainty. It keeps one-use plan confirmation and job status; it does not start a download to learn its size. [LM Studio download API](https://lmstudio.ai/docs/developer/rest/download).
- [ ] Discover LM Studio's actual configured storage path automatically. An explicitly configured `models_path` can now be checked for free space on Mac or Alfred; unknown paths remain unverified.

## Current additions: measured routing and request lifecycle

- [x] Prompt-free local benchmark metrics for 3–12 reviewed cases per profile; recent pass rate and latency can influence `pair_smart_ask`.
- [x] Background jobs with stage/progress updates, partial response, cancellation and journal-backed recovery metadata; no prompt or answer is written to the journal.
- [ ] Run representative live benchmark suites on both devices and verify a successful long-running job after the async streaming change.

## Delivery workflow

- [x] Use **Graphify** to map affected code paths and refresh the graph after code changes in the temporary analysis copy; generated graph remains outside the project.
- [x] Use **zvec-grep** for semantic/cross-file retrieval and `rg` for exact identifiers. Temporary local install and index used; index remains outside the project.
- [x] Apply **ProofLoop** methodology: acceptance conditions, tests and real-device checks are recorded in `docs/proof/SMART_ROUTING_PROOF.md`. No `proofloop` CLI was run.
- [x] Update English and Russian documentation with setup, limits, privacy implications and failure cases; OMP and Jev live verification limits are explicit.

## Sources

- [OMP project](https://omp.sh/) and [source repository](https://github.com/can1357/oh-my-pi)
- [TypeSafe AI / Jev](https://typesafe.ai/)
- [LM Studio native API](https://lmstudio.ai/docs/developer/rest)
- [zvec-grep](https://github.com/zvec-ai/zvec-grep)

## Delivered sequence 5 → 1 → 2 → 3 → 4 → 6

- [x] 5. Redacted per-request diagnostics (`docs/proof/05-diagnostics.md`).
- [x] 1. Live inventory and in-lock recheck (`docs/proof/01-inventory.md`).
- [x] 2. Profile-based installed-model selection (`docs/proof/02-profiles.md`).
- [x] 3. Two-model comparison with provenance and explicit source-verification workflow; actual findings require Codex file review.
- [x] 4. Per-device queues, context-aware memory-estimate budgets, live stages and observed eviction reporting; see `docs/proof/04-resources.md`.
- [x] 6. Project/plugin marketplace renamed to pair-bridge; legacy config filename retained for compatibility.
