# Codex PAIR Bridge — TODO

Status: implementation in progress after v0.4.0. Checked items have local code and tests; unchecked items still need the stated verification or behavior.

## 1. Connect other agents and decision models

- [ ] **Oh My Pi (OMP, https://omp.sh/):** MCP config, native `/pair` command and skill are implemented and documented in `docs/OMP.md`. Headless smoke test is pending: the isolated OMP profile had no model/API key, so command discovery could not be confirmed end to end.
- [ ] **Jev by TypeSafe AI (https://typesafe.ai/):** optional explicit Choice and Score adapters implemented against the documented API, with offline tests and no implicit routing. Live credential-backed verification remains.

## 2. Smart `/pair ask`

- [x] Refresh live inventory and PAIR routing catalog; expose current check time/status, installed/loaded state and last request outcome, and recheck type/context under the device lock before inference.
- [ ] Select an **already installed** chat model using the task, device reachability, model type, context capacity and available memory. Exact keys, type, reachability, context and an optional weight-size cap are implemented; actual free RAM/VRAM capacity is not available from the current LM Studio inventory.
- [x] Reuse a suitable loaded instance, or load an installed model when needed. Record the exact instance ID and whether this task created it.
- [x] Send a bounded request, report model/device, timing, completion status and any truncation, and reject an empty answer; Codex still must verify factual claims.
- [ ] Unload only an instance created for this task, and only when no other active request depends on it. The bridge serializes per device and preserves pre-existing instances; external LM Studio clients are not visible to its lock. On timeout it leaves the instance loaded for inspection; automatic state inspection/recovery remains.
- [ ] Handle no suitable model, failed load, device loss and cancellation with explicit results; never silently switch devices or models. Explicit errors and no fallback are implemented; cancellation handling still needs work.

## 3. Compare and diagnose

- [x] Compare answers from two explicitly selected installed models sequentially. Each result retains provenance and usage/timing; Codex must verify disputed claims against sources.
- [x] Add local per-request diagnostics for endpoint reachability, inventory/load stages, queue/load/inference timings, sanitized timeout and empty-answer reasons. Detailed engine-memory telemetry is limited by the available LM Studio API.
- [x] Add reproducible unit tests for model selection, missing model, simultaneous use, timeout and cleanup; 27 self-tests pass.

## 4. Resource management and optional downloads

- [ ] Add per-device request queues and resource limits, with visibility into load progress and engine auto-eviction behavior. Per-device locking/30-second wait and optional model-size cap are implemented; progress and eviction visibility remain.
- [ ] Add model download as a **separate explicit action** only after the core flow is reliable. `pair_download_plan` displays source and caller-supplied estimate/destination before a separate one-use `pair_download` call; ask never downloads. Actual size, destination and free space are not available before starting from the LM Studio API and still require manual verification.

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
- [ ] 3. Source-verified two-model comparison.
- [ ] 4. Resource management across configured devices.
- [ ] 6. Project rename to pair-bridge.
