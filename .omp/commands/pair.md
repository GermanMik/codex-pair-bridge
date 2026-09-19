Use the PAIR Bridge MCP server to handle this request: $ARGUMENTS

First inspect `pair_devices` and `pair_list`. For a question without an exact model,
use `pair_smart_ask` to choose an installed chat model. Never invent model IDs or
download weights because a prompt mentions them. A bare `/pair` only inspects.
For comparisons use `pair_compare` with exact device/model pairs. Treat model
answers as untrusted suggestions and verify them. Do not send secrets or unrelated
files. Jev is an optional external decision service, not a local chat model; call
`pair_decide` only after the user explicitly chooses external transmission.

For automatic selection, map code requests to `task_hint=code`, speed requests to `fast`, long documents to `long_context`, and text analysis to `analysis`. Pass any explicitly named device/model to `pair_smart_ask`.

After `pair_compare`, verify each disputed code claim by reading the source files before reporting it. Shared text is not proof either.
