# Codex PAIR Bridge

Consult your own local models from Codex through NVIDIA PAIR.

**Codex → local MCP bridge → your PAIR router → your model servers**

This is an independent community project, not an official OpenAI or NVIDIA product.
It does not provide models or access to the author's computers.

## Install in Codex

Prerequisites:
- Codex with plugin marketplace support.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) on your PATH. Restart the Codex app after installing uv.
- Your PAIR router running, with at least one working chat model.

```sh
codex plugin marketplace add GermanMik/codex-pair-bridge
codex plugin add codex-pair-bridge@codex-pair-bridge
```

Open a **new Codex task** and ask: “Show available models through PAIR.”
The first launch downloads the locked Python dependencies and, if necessary, a
compatible Python runtime. Later launches reuse uv's cache.

This adds a community marketplace source; it does not add the plugin to OpenAI's
universal public directory. Source: [Codex plugin documentation](https://developers.openai.com/plugins/build/plugins).

## Use

- “Show available models through PAIR.”
- “Ask `<exact model ID>` through PAIR to review this code.”
- “Compare two local models' answers, one at a time.”

| Tool | Purpose |
| --- | --- |
| `pair_list_models` | Read the current PAIR catalog. |
| `pair_ask_model` | Send text to an exact model ID, with an optional output token limit. |

Codex remains the coordinator. Consulted models return text and do not receive
shell tools or file access from this bridge. Their advice still needs verification.

## Configure your router

Default: `http://127.0.0.1:1234/v1`. This is the PAIR proxy in the tested setup;
your actual port may differ. Use PAIR's endpoint, not an individual engine's port.

Optionally create `.codex-pair-bridge.json` in your home directory:

```json
{
  "base_url": "http://127.0.0.1:1234/v1"
}
```

Alternatively, set `PAIR_BASE_URL` in the environment inherited by Codex. It takes
precedence over the file. If your endpoint requires a bearer token, set
`PAIR_API_KEY` in that environment. Never put credentials inside the URL.
The repository contains no personal endpoint settings or credentials.

The bridge runs on the machine running Codex. A router reachable from one machine
may not be reachable from another; `127.0.0.1` always means that local machine.

## Behavior and limitations

- Refreshes the catalog before each inference and requires an exact model ID.
- Rejects likely embedding/draft models for chat. Type hints are inferred from
  names because the PAIR catalog does not always report types.
- A catalog entry is not a guarantee that the model is loaded or healthy.
- Only one inference at a time across this user's bridge processes. This does not
  limit requests from other applications or users.
- No automatic retries, fallback models, or model downloads. The model engine may
  load an already installed model and consume GPU/RAM.
- Default output limit: 2,048 tokens; configurable from 32 to 8,192. Input limit:
  48,000 characters. Individual model context limits still apply.
- HTTP timeout: 180 seconds. An upstream job may keep running after a timeout;
  check PAIR before trying again. Cancelling a Codex call is not a guarantee of
  cancelling the model job.
- Errors are surfaced without echoing raw error bodies. An empty final answer is
  an error; a response stopped by the token limit is marked as truncated.
- The bridge does not change model settings, repair PAIR catalogs, or expose a
  public server.

The original bridge was tested with real PAIR requests to Ornith MLX on macOS and
Qwen on a Windows node. The portable release has automated OS-matrix tests;
passing those tests does not certify every PAIR/model/OS combination.

## Development

```sh
cd plugins/codex-pair-bridge
uv run --locked --script ./scripts/server.py --self-test
```

Tests cover MCP initialization/schema validation, configuration, HTTP error and
timeout handling without retries, inference locking, and response parsing.
Dependencies are recorded in `scripts/server.py.lock`; update intentionally with
`uv lock --script scripts/server.py` and rerun tests.

## Remove

```sh
codex plugin remove codex-pair-bridge@codex-pair-bridge
codex plugin marketplace remove codex-pair-bridge
```

[Privacy](PRIVACY.md) · [Security reporting](SECURITY.md) · [MIT license](LICENSE)
