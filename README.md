<div align="center">

# PAIR Bridge

### One `/pair` command for the models on all your devices

## Your local models, one conversation with Codex.

[English](README.md) · [Русский](README.ru.md) · [Installation](#get-started) · [Troubleshooting](#troubleshooting)

![How Codex uses MCP tools to ask local models through PAIR](docs/assets/mcp-explained.png)

[![Tests](https://github.com/GermanMik/pair-bridge/actions/workflows/test.yml/badge.svg)](https://github.com/GermanMik/pair-bridge/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-mint.svg)](LICENSE)

</div>

Ask a local model for a code review, a second opinion, or an alternative solution—without leaving your Codex task. **PAIR Bridge gives Codex tools for consulting PAIR and managing configured LM Studio devices.**

Type `/pair` and choose the **pair** skill, or mention `$pair`. Astra, Sol, and other tool-capable Codex models can then inspect your devices, load an installed model, ask it a bounded question, and unload the exact instance they started.

> `/pair find a suitable model on pc, load it, and ask it to review this function`

The bridge never downloads a model just because a prompt names it. It first reads the live inventory, so a stale or nonexistent entry such as `gpt-oss-20b` is reported instead of being requested blindly.

Independent community project. Not affiliated with or endorsed by OpenAI or NVIDIA.

## What does MCP actually do?

**MCP means Model Context Protocol.** It is the interface through which Codex discovers tools and calls them. In this project, a small MCP server runs on your computer and exposes tools for discovery, model lifecycle, and inference.

Think of the workflow as four jobs:

| Component | Its job | Example |
| --- | --- | --- |
| **Codex** | Understand your task and use the returned answer. | “I need a second opinion on this function.” |
| **MCP bridge** | Expose discovery, lifecycle, and inference as tools. | Inspect a device, load a model, then call it. |
| **PAIR** | Route requests when no device is selected. | Send the request to a connected model server. |
| **Local model** | Generate an answer. | Return review comments to Codex. |

**MCP is the tool connection; PAIR is the model router.** The bridge does not turn a local model into the main Codex model. Codex continues coordinating your task, and the consulted model returns text for Codex to assess.

## A real example

> **You:** “Use `pair_list`, then `pair_ask` to review this function for edge cases.”
>
> **Codex:** Reads the current model list, selects an appropriate chat model, and sends the relevant code through the bridge.
>
> **Local model:** Returns its review.
>
> **Codex:** Checks the suggestions against your code and explains which changes are worth making.

The consulted model receives the text passed to the tool. This bridge gives it no shell tools or direct access to your files.

## Get started

### 1 · Prepare your local models

You need:

- **Codex** with plugin marketplace support.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** installed and available on your PATH.
- **PAIR running**, connected to at least one working chat model, for routed requests.
- **LM Studio 0.4+** with its native API enabled on each device you want Codex to manage.
- **OpenSSH** and a working SSH config alias for remote loopback-only LM Studio endpoints.

After installing uv, restart Codex so it can discover it. Confirm uv is available with `uv --version`.

### 2 · Install the plugin

Run these commands in a terminal:

```sh
codex plugin marketplace add GermanMik/pair-bridge
codex plugin add pair-bridge@pair-bridge
```

This adds our GitHub marketplace to Codex. It is a community catalog, separate from OpenAI's universal plugin directory. [About plugin marketplaces](https://developers.openai.com/plugins/build/plugins).

The first tool launch downloads the locked dependencies and, if needed, a compatible Python runtime. Subsequent launches reuse the cache.

### 3 · Start a new Codex task

Try the skill first:

> `/pair show my devices and available models`

Then ask it to operate on a device:

> `/pair load a suitable installed chat model on pc, ask it to check this function, then unload the instance you started`

You should get a model answer that Codex can use in the conversation. The model list alone does not confirm that every listed model can load successfully.

## Prompts to try

| Goal | Ask Codex |
| --- | --- |
| Inspect everything | “`/pair show configured devices and the PAIR routing catalog.`” |
| Review on one device | “`/pair use pc to review this code for bugs.`” |
| Get another approach | “`/pair ask a suitable available model for an alternative, then evaluate its answer.`” |
| Compare devices | “`/pair ask one model on mac and one on pc, then compare their answers.`” |

Model names differ between installations. Let `/pair` inspect the live catalog before it selects one.

## Connect your PAIR router

The default address is **`http://127.0.0.1:1234/v1`**. This is the PAIR proxy in the tested setup. Check the endpoint displayed by your PAIR installation if it uses a different port.

To change it, create **`.pair-bridge.json` in your home directory**:

```json
{
  "base_url": "http://127.0.0.1:1234/v1"
}
```

| System | Configuration file |
| --- | --- |
| macOS / Linux | `~/.pair-bridge.json` |
| Windows | `%USERPROFILE%\.pair-bridge.json` |

Use your **PAIR router's endpoint**. An individual LM Studio endpoint only provides that server's models. `127.0.0.1` refers to the computer running the bridge.

<details>
<summary><strong>Environment variables and authentication</strong></summary>

`PAIR_BASE_URL` overrides the configuration file. Set it in the environment inherited by Codex.

If your endpoint requires a bearer token, set `PAIR_API_KEY` in that environment. Credentials must not be embedded in the URL or committed to the repository.

</details>

## Configure managed devices

Add native LM Studio API origins to the same configuration file. These are separate from the PAIR proxy URL:

```json
{
  "base_url": "http://127.0.0.1:1234/v1",
  "devices": [
    {"id": "mac", "engine": "lmstudio", "base_url": "http://127.0.0.1:1235"},
    {"id": "pc", "engine": "lmstudio", "base_url": "http://127.0.0.1:1235", "ssh_host": "my-pc"}
  ]
}
```

Use the real native API origin from each LM Studio installation; the ports above are examples. `ssh_host` must be an existing OpenSSH config alias. The bridge opens a temporary loopback-only tunnel with host-key checking, runs no remote shell command, and closes the tunnel after the request. A direct HTTPS origin is also supported.

Each device may set `max_loaded_bytes` to a positive weight-size budget. Bridge rejects a cold load if currently loaded model weights plus the candidate exceed it; this conservative estimate excludes KV cache and runtime overhead. Calls wait up to 30 seconds in a per-device queue, and `/pair diagnose` shows queued/loading/inference stages while active. Load results include LM Studio load time and any instances that disappeared during loading. Bridge only auto-unloads the exact instance it loaded for the request. [LM Studio Idle TTL and Auto-Evict](https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict) apply to JIT loads according to server settings; Bridge does not change those settings.

Devices are configured explicitly. PAIR peer discovery does not grant model-management access. Ollama lifecycle management, model deletion, engine installation, and PAIR cluster administration are not implemented. The separate `pair_download` tool requires a one-use `pair_download_plan` and the exact model ID repeated in `confirm_model`; it is never used by `pair_ask` or `pair_smart_ask`.

For an authenticated device, set `api_key_env` to the name of an environment variable containing its token and pass that variable to the MCP process through `.mcp.json` `env_vars`. Keep tokens out of configuration committed to Git and out of prompts.

## What stays local?

The bridge runs on your computer and sends requests to **your configured PAIR endpoint**. PAIR can route them to your connected model servers. The project maintainer receives no requests through this plugin.

**The complete Codex conversation is not necessarily local.** Model answers return to Codex and follow your Codex/OpenAI data settings. PAIR and model servers may also keep their own logs. [Read the privacy note](PRIVACY.md).

## Troubleshooting

| What you see | What to check |
| --- | --- |
| Tools do not appear | Open a new task; verify the plugin is enabled and `uv` is on Codex's PATH. |
| Cannot reach PAIR | Start PAIR and check its endpoint against the configuration file. |
| A configured device is unreachable | Verify its LM Studio native API, port, and direct HTTPS or SSH connection. |
| A model is listed but fails | Inspect PAIR's job details and model-server logs. Catalog entries are not health checks. |
| A named model is not installed | Run `/pair` inventory and choose an exact installed key; the bridge does not download missing weights. |
| HTTP 400 or 500 | Check the exact model ID, model loading, memory availability, and server errors. |
| Another request is running | Wait for the current bridge call to finish. |
| Timeout | Check PAIR before retrying: the model job may still be running. |
| No final text | The model may have spent its output budget on reasoning; inspect the result before choosing a larger budget. |

## Slash command and MCP tools

`/pair` activates the skill that teaches Codex how to plan safe model operations. The names below are MCP tools used by that skill. They are not terminal commands.

Without `device`, `pair_list` and `pair_ask` use the PAIR router. With `device`, they target that configured LM Studio instance directly. Direct inference requires exactly one loaded instance of the selected model key.

**`pair_ask`** — requires `model` (an exact ID from `pair_list`) and `prompt` (your question). Optional `max_tokens` defaults to `2048`.

Example arguments for `pair_ask` (replace the model ID):

```json
{
  "model": "<exact ID from pair_list>",
  "prompt": "Review this function for edge cases: ...",
  "max_tokens": 2048
}
```

## Tool reference

| Tool | Inputs | Returns |
| --- | --- | --- |
| `pair_devices` | None | Reachability plus installed and loaded model inventory for every configured device. |
| `pair_list` | Optional `device` | PAIR catalog, or native inventory for one device. |
| `pair_load` | `device`, `model`, optional `context_length` | Reused or newly loaded instance and its exact instance ID. |
| `pair_unload` | `device`, `instance_id` | Confirmation that one exact instance is no longer observed. |
| `pair_ask` | `model`, `prompt`, optional `device`, `max_tokens` | Answer, selected model, completion status, timing and usage when available. |
| `pair_smart_ask` | `prompt`; optional `model`, `device`, `task_hint` (`general`, `code`, `fast`, `long_context`, `analysis`), `context_length`, `max_tokens`, `unload_after` | Chooses from live installed device inventories, loads if needed, asks once and reports cleanup. No download or silent fallback. |
| `pair_compare` | `prompt`, two exact device/model pairs | Two sequential results with provenance and textual disagreements; Codex verifies claims against source. |
| `pair_diagnose` | None | Router/device health and recent local request stages, durations, and sanitized failure reasons; no prompts or tokens. |
| `pair_download_plan` / `pair_download` / `pair_download_status` | Exact model, reviewed size/destination, one-use plan ID, repeated `confirm_model`; job ID | Review source and caller-supplied estimate before a separate explicit start. LM Studio reports actual bytes only after starting; verify free space and storage settings yourself. |
| `pair_decide` / `pair_score` | State, Choice options or ordered Score levels, `allow_external=true` | Optional typed evaluation from **external** TypeSafe AI Jev; requires `TYPESAFE_API_KEY`. |

The smart path requires at least one explicitly configured, online LM Studio device. It preserves pre-existing loaded instances. An instance loaded for a successful smart request is unloaded by default; an inference error or timeout leaves it loaded for inspection. Other applications can use the same LM Studio server, so Bridge cannot guarantee an instance is idle outside its own calls. Set `unload_after=false` when sharing a model with other clients.

Oh My Pi users can use the same MCP server and a native `/pair` command. See the [OMP setup guide](docs/OMP.md). Jev is a separate cloud decision service, never a local chat fallback; the bridge sends no state to it without an explicit `allow_external=true` call. [TypeSafe API reference](https://docs.typesafe.ai/api).

<details>
<summary><strong>Limits and request behavior</strong></summary>

- Exact model IDs only; the catalog is refreshed before inference.
- Likely embedding and draft models are rejected for chat. Type hints are inferred from names.
- Load, unload, and inference operations are queued per configured device across this user's bridge processes. Router calls use a separate lock because the destination is unknown. Other applications are outside these limits.
- No automatic retries, fallback models, or downloads during a model request. The engine may load an already installed model and consume GPU/RAM.
- Default output budget: 2,048 tokens; allowed range: 32–8,192. Input: up to 48,000 characters. Model context limits still apply.
- Request timeout: 180 seconds. Cancellation or timeout does not guarantee cancellation of the upstream model job.
- Empty final answers are errors. Answers stopped by the output budget are marked as truncated.
- Unloading affects the exact LM Studio instance and can disrupt another application that uses it. The skill tracks task-owned loads and avoids unloading unrelated instances.
- The bridge does not change persistent engine settings or repair model catalogs. Explicit loads can set context length.

</details>

## Migrating from `codex-pair-bridge`

The marketplace and plugin IDs are now `pair-bridge`. Existing `~/.codex-pair-bridge.json` configuration remains readable; the new `~/.pair-bridge.json` takes precedence if both exist. The local diagnostic cache keeps its old directory name to preserve request history. For an existing installation, run:

```sh
codex plugin remove codex-pair-bridge@codex-pair-bridge
codex plugin marketplace remove codex-pair-bridge
codex plugin marketplace add GermanMik/pair-bridge
codex plugin add pair-bridge@pair-bridge
```

## Update from an earlier version

```sh
codex plugin marketplace upgrade pair-bridge
codex plugin add pair-bridge@pair-bridge
```

Open a new task after updating so Codex discovers the `/pair` skill and current MCP tools. Version 0.5.0 adds smart selection, comparison, diagnostics, resource limits, OMP integration and optional Jev tools under the new `pair-bridge` plugin ID.

## For contributors

```sh
cd plugins/pair-bridge
uv run --locked --script ./scripts/server.py --self-test
```

The automated tests cover MCP initialization, argument validation, configuration, SSH tunnel planning, device inventory, lifecycle operations, errors, timeouts, locking and response parsing. CI runs on **macOS, Windows and Linux**. Real routed and device-targeted requests were tested on macOS and a remote Windows node for the earlier release; new workflows still require device-specific acceptance runs.

Dependencies are locked in `scripts/server.py.lock`. Update intentionally with `uv lock --script scripts/server.py`, then rerun tests.

<details>
<summary><strong>Uninstall</strong></summary>

```sh
codex plugin remove pair-bridge@pair-bridge
codex plugin marketplace remove pair-bridge
```

</details>

---

[Report an issue](https://github.com/GermanMik/pair-bridge/issues) · [Privacy](PRIVACY.md) · [Security](SECURITY.md) · [MIT license](LICENSE)
