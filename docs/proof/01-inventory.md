# ProofLoop 01: reliable model inventory

Acceptance: `/pair` exposes reachability, installed key, loaded state, context limit, check time and last request outcome. A smart ask rechecks type and context after acquiring the device lock; a stale/nonexistent key must never start inference or download.

Evidence: `test_checked_inventory_shows_load_state_and_last_result`, `test_smart_ask_rechecks_type_before_inference`, `test_selector_prefers_loaded_installed_chat` and `test_no_download_for_missing_model`; 34 self-tests passed. PAIR MCP inventory showed Mac online with a loaded Ornith LLM and Alfred offline. The isolated test process could not reach the Mac endpoint, so new inventory formatting is unit-tested but not live-verified through that process.
