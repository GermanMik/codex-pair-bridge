# ProofLoop 06: project rename

Acceptance: the repository, marketplace, plugin manifest, plugin folder, CI path and install documentation use `pair-bridge`. The MCP server identifies as `pair-bridge`. Existing `~/.codex-pair-bridge.json` remains readable; `~/.pair-bridge.json` wins when both exist. Existing request-journal cache path remains for continuity.

Evidence: `test_new_config_takes_precedence_over_legacy`, existing config test, full 40-test MCP suite, plugin manifest validator and skill validator passed. The repo marketplace was generated with the plugin-creator scaffold. GitHub repository rename is an external final step after the rename commit is pushed.
