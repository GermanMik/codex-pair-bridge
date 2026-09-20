# PAIR Bridge — TODO

Status: implementation in progress. Checked items have local code and tests; unchecked items still need the stated verification or behavior. Current validation: 47 self-tests passed.

## 1. Connect other agents and decision models

- [ ] **Oh My Pi (OMP, https://omp.sh/):** MCP config, native `/pair` command and skill are implemented and documented in `docs/OMP.md`. Headless smoke test is pending: the isolated OMP profile had no model/API key, so command discovery could not be confirmed end to end.
- [ ] **Jev by TypeSafe AI (https://typesafe.ai/):** optional explicit Choice and Score adapters implemented against the documented API, with offline tests and no implicit routing. Live credential-backed verification remains.

## 2. Smart `/pair ask`

- [x] Refresh live inventory and PAIR routing catalog; expose current check time/status, installed/loaded state and last request outcome, and recheck type/context under the device lock before inference.
- [ ] Select an **already installed** chat model using the task, device reachability, model type, context capacity and available memory. Exact keys, type, reachability and context are checked; cold loads use a context-aware CLI estimate and optional configured memory budget. Actual free RAM/VRAM is not available from the LM Studio inventory, so automatic capacity-aware ranking remains open.
- [x] Reuse a suitable loaded instance, or load an installed model when needed. Record the exact instance ID and whether this task created it.
- [x] Send a bounded request, report model/device, timing, completion status and any truncation, and reject an empty answer; Codex still must verify factual claims.
- [ ] Unload only an instance created for this task, and only when no other active request depends on it. The bridge serializes per device and preserves pre-existing instances; external LM Studio clients are not visible to its lock. On timeout it leaves the instance loaded for inspection; automatic state inspection/recovery remains.
- [ ] Handle no suitable model, failed load, device loss and cancellation with explicit results; never silently switch devices or models. Explicit errors and no fallback are implemented; cancellation handling still needs work.

## 3. Compare and diagnose

- [x] Compare answers from two explicitly selected installed models sequentially. Each result retains provenance and usage/timing; Codex must verify disputed claims against sources.
- [x] Add local per-request diagnostics for endpoint reachability, inventory/load stages, queue/load/inference timings, sanitized timeout and empty-answer reasons. Detailed engine-memory telemetry is limited by the available LM Studio API.
- [x] Add reproducible tests for model selection, missing model, simultaneous use, timeout, cleanup, memory preflight, download review and MCP discovery; 47 self-tests pass.

## 4. Resource management and optional downloads

- [x] Add per-device 30-second queues, configurable memory-estimate budgets, live queue/preflight/load/inference stage records, load time and observed engine evictions. Exact free RAM/VRAM and streamed load percentage are not exposed by the synchronous LM Studio load endpoint.
- [x] Replace the weight-size gate with a context-aware `lms load --estimate-only` preflight for cold loads; include existing instances at their actual contexts, apply 10% headroom to configured memory budgets, expose read-only `pair_memory_plan`, and mark missing estimates unknown. Alfred live check returned Qwen 27B at 8,192 plus Ornith at its loaded 65,536 context. No weights were loaded. [LM Studio CLI](https://lmstudio.ai/docs/cli/local-models/load), [model inventory](https://lmstudio.ai/docs/developer/rest/list).
- [ ] Measure actual free RAM/VRAM per device and calibrate CLI estimates against observed usage where supported. The LM Studio native inventory does not expose free capacity; `max_loaded_bytes` remains a user-configured budget, not detected hardware capacity. GPU offload and parallel settings may also change estimates.
- [x] Keep downloads a **separate explicit action**, never part of ask. `pair_download_plan` now checks public Hugging Face metadata for one unambiguous GGUF file and local destination free space with 10% headroom; catalog IDs and ambiguous/sharded files retain a caller estimate with uncertainty. It keeps one-use plan confirmation and job status; it does not start a download to learn its size. [LM Studio download API](https://lmstudio.ai/docs/developer/rest/download).
- [ ] Verify LM Studio's actual configured storage path and remote-device free space before claiming a destination is checked. The API does not expose these settings; current plans label them unverified.

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
