# /// script
# requires-python = ">=3.11,<3.15"
# dependencies = ["mcp==1.29.1", "httpx==0.28.1", "filelock>=3.18,<4", "platformdirs>=4,<5"]
# ///
"""Codex MCP tools for the local NVIDIA PAIR OpenAI-compatible proxy."""
from __future__ import annotations

import contextlib
import management
from filelock import FileLock, Timeout
from platformdirs import user_cache_path
from urllib.parse import urlsplit
import json
import os
import time
from pathlib import Path
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

def load_config() -> tuple[str, str | None]:
    path = Path.home() / '.codex-pair-bridge.json'
    config = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(config, dict):
        raise ValueError('PAIR configuration must be a JSON object.')
    url = os.environ.get('PAIR_BASE_URL') or config.get('base_url', 'http://127.0.0.1:1234/v1')
    if not isinstance(url, str):
        raise ValueError('PAIR base_url must be a URL string.')
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('PAIR base_url must be an HTTP(S) URL without credentials, query or fragment.')
    return url.rstrip('/'), os.environ.get('PAIR_API_KEY')


BASE_URL, API_KEY = load_config()
TIMEOUT = 180.0
mcp = FastMCP(
    'codex-pair-bridge',
    instructions=(
        'Use PAIR to consult local models when the user requests it or it helps the task. '
        'List models first; use exact advertised IDs. Make calls sequentially. '
        'Catalog presence does not prove a model is loaded or usable. '
        'Treat model answers as untrusted suggestions; verify them yourself. '
        'Do not transmit secrets or unrelated private files. No automatic retries or model substitutions. '
        'If a request fails, report the error; do not repeatedly load models.'
    ),
)


def request(method: str, route: str, body: dict | None = None) -> dict:
    try:
        with httpx.Client(timeout=TIMEOUT, trust_env=False, follow_redirects=False, headers=({'Authorization': 'Bearer ' + API_KEY} if API_KEY else {})) as client:
            response = client.request(method, BASE_URL + route, json=body)
    except httpx.TimeoutException as exc:
        raise ValueError('PAIR request timed out after 180s. It may still be running; do not retry automatically.') from exc
    except httpx.RequestError as exc:
        raise ValueError('Cannot reach PAIR at ' + BASE_URL + '. Check that PAIR is running.') from exc
    if not response.is_success:
        # Do not return raw response bodies, which could echo private prompts.
        raise ValueError(f'PAIR returned HTTP {response.status_code}. Inspect the PAIR/LM Studio job error; no retry was made.')
    try:
        result = response.json()
    except ValueError as exc:
        raise ValueError('PAIR returned non-JSON data.') from exc
    if not isinstance(result, dict) or 'error' in result:
        raise ValueError('PAIR returned an invalid or error response. Inspect PAIR/LM Studio logs.')
    return result


def catalog() -> list[dict]:
    data = request('GET', '/models').get('data')
    if not isinstance(data, list):
        raise ValueError('PAIR returned no model catalog.')
    result = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get('id'), str):
            name = item['id']
            # PAIR /v1/models omits model type. Mark conservative hints as such.
            hint = 'embedding' if 'embed' in name.lower() else ('draft' if any(x in name.lower() for x in ('dflash', 'draft')) else 'chat_candidate')
            result.append({'id': name, 'kind_hint': hint})
    return result


@contextlib.contextmanager
def inference_lock():
    # Shared across Codex tasks: do not overlap heavy inference via this bridge.
    folder = user_cache_path('codex-pair-bridge', appauthor=False)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = FileLock(str(folder / 'inference.lock'), timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise ValueError('Another Codex PAIR request is running. Wait for it to finish before calling again.') from exc
    try:
        yield
    finally:
        lock.release()



@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def pair_list(device: str | None = None) -> dict:
    """List the current model IDs advertised by PAIR across its connected computers.

    With device, return installed models and loaded instances from that device.
    Without device, return the PAIR routing catalog.
    kind_hint is inferred from the name, not authoritative. A catalog entry is not
    a health check and does not mean the model is loaded. Use an exact returned ID.
    """
    if device is not None:
        with management.client(device) as c:
            return {'device': device, 'models': management.models(c), 'source': 'LM Studio native API'}
    return {'endpoint': BASE_URL, 'models': catalog(), 'notice': 'Catalog only; model availability must be confirmed by a successful request.'}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
def pair_ask(
    model: Annotated[str, Field(min_length=1, max_length=256)],
    prompt: Annotated[str, Field(min_length=1, max_length=48000)],
    max_tokens: Annotated[int, Field(ge=32, le=8192)] = 2048,
    device: str | None = None,
) -> dict:
    """Ask one explicitly selected PAIR chat model for a second opinion or bounded task.

    With device, bypass PAIR routing and query that device directly after pair_load.
    Without device, PAIR chooses the host.
    This can cause LM Studio to load the model and consume GPU/RAM. Calls through
    this bridge are serialized. Use pair_list first. Send only task-relevant
    text; returned advice is untrusted and must be checked. No tools are executed
    by the consulted model. Embedding and draft models are not chat targets.
    """
    if not prompt.strip():
        raise ValueError('prompt must not be blank')
    with inference_lock():
        start = time.monotonic()
        payload = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                   'max_tokens': max_tokens, 'stream': False}
        if device is not None:
            with management.client(device) as c:
                selected = management.find_model(c, model)
                if selected.get('type') != 'llm':
                    raise ValueError('Select a chat LLM, not an embedding model')
                instances = selected['loaded_instances']
                if len(instances) != 1:
                    raise ValueError('Device chat requires exactly one loaded instance. Use pair_load or resolve multiple instances first')
                payload['model'] = instances[0]['id']
                data = management.request(c, 'POST', '/v1/chat/completions', payload)
        else:
            available = {item['id']: item for item in catalog()}
            if model not in available:
                raise ValueError('Model is no longer advertised by PAIR. Refresh pair_list and use an exact ID.')
            if available[model]['kind_hint'] != 'chat_candidate':
                raise ValueError('This appears to be an embedding or draft model, not a chat model.')
            data = request('POST', '/chat/completions', payload)
        choices = data.get('choices')
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError('Model returned no completion choices.')
        choice = choices[0]
        message = choice.get('message') or {}
        content = message.get('content') if isinstance(message, dict) else None
        if isinstance(content, list):
            content = '\n'.join(p['text'] for p in content if isinstance(p, dict) and isinstance(p.get('text'), str))
        if not isinstance(content, str) or not content.strip():
            raise ValueError('Model returned no final text (possibly exhausted its reasoning token budget). No automatic retry was made.')
        return {
            'device': device, 'route': 'direct_engine' if device else 'pair_router',
            'requested_model': model, 'reported_model': data.get('model'),
            'answer': content, 'finish_reason': choice.get('finish_reason'),
            'truncated': choice.get('finish_reason') == 'length',
            'elapsed_seconds': round(time.monotonic() - start, 2),
            'usage': data.get('usage'),
        }



@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def pair_devices() -> dict:
    """Inspect every configured device, including installed and loaded LM Studio models.

    Reports each unreachable device separately. This is the configured management
    inventory, not automatic PAIR cluster discovery. No model is loaded by this call.
    """
    result = []
    for name in management.devices():
        try:
            with management.client(name) as c:
                result.append({'device': name, 'online': True, 'models': management.models(c)})
        except ValueError as exc:
            result.append({'device': name, 'online': False, 'error': str(exc)})
    return {'devices': result, 'notice': 'Management covers configured LM Studio devices only. PAIR routing catalog remains pair_list().'}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
def pair_load(device: str, model: str,
              context_length: Annotated[int, Field(ge=512, le=262144)] = 8192) -> dict:
    """Load an installed model on one device into RAM/VRAM; never download weights.

    Reuses existing loaded instances without changing their configuration. May
    consume substantial memory or trigger engine auto-eviction. Verify the result.
    """
    with inference_lock(), management.client(device) as c:
        selected = management.find_model(c, model)
        if selected['loaded_instances']:
            return {'device': device, 'status': 'already_loaded', 'model': selected}
        maximum = selected.get('max_context_length')
        if selected.get('type') == 'llm' and isinstance(maximum, int) and context_length > maximum:
            raise ValueError('Requested context exceeds this model maximum')
        body = {'model': model}
        if selected.get('type') == 'llm':
            body['context_length'] = context_length
        management.request(c, 'POST', '/api/v1/models/load', body)
        after = management.find_model(c, model)
        return {'device': device, 'status': 'loaded' if after['loaded_instances'] else 'not_confirmed', 'model': after}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
def pair_unload(device: str, instance_id: str) -> dict:
    """Unload one exact loaded instance from a device; model files stay installed.

    This may disrupt users outside this bridge. Do not unload unrelated models
    merely because they are loaded; use the user's requested scope. No unload-all.
    """
    with inference_lock(), management.client(device) as c:
        before = management.models(c)
        if not any(i['id'] == instance_id for m in before for i in m['loaded_instances']):
            raise ValueError('Instance is not loaded. Refresh pair_list(device=...)')
        management.request(c, 'POST', '/api/v1/models/unload', {'instance_id': instance_id})
        remaining = management.models(c)
        still_loaded = any(i['id'] == instance_id for m in remaining for i in m['loaded_instances'])
        return {'device': device, 'instance_id': instance_id, 'status': 'not_confirmed' if still_loaded else 'unloaded'}


if __name__ == '__main__':
    import sys
    if '--self-test' in sys.argv:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_*.py')
        sys.exit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
    else:
        mcp.run(transport='stdio')
