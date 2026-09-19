# /// script
# requires-python = ">=3.11,<3.15"
# dependencies = ["mcp==1.29.1", "httpx==0.28.1", "filelock>=3.18,<4", "platformdirs>=4,<5"]
# ///
"""Codex MCP tools for the local NVIDIA PAIR OpenAI-compatible proxy."""
from __future__ import annotations

import contextlib
import difflib
import management
import jev
import diagnostics
from filelock import FileLock, Timeout
from platformdirs import user_cache_path
from urllib.parse import urlsplit
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
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
_DOWNLOAD_PLANS: dict[str, dict] = {}
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


def checked_models(device: str, rows: list[dict]) -> list[dict]:
    """Attach current inventory status and last request outcome without storing prompts."""
    checked_at = datetime.now(timezone.utc).isoformat()
    recent = diagnostics.recent(100)
    enriched = []
    for item in rows:
        last = next((r for r in reversed(recent) if r.get('device') == device and
                     r.get('model') == item['key']), None)
        enriched.append(dict(item, availability='online',
                             load_state='loaded' if item['loaded_instances'] else 'installed_unloaded',
                             checked_at=checked_at, last_request_status=last.get('status') if last else 'not_checked',
                             last_request_reason=last.get('reason') if last else None))
    return enriched


def completion(data: dict, requested_model: str, device: str | None, started: float) -> dict:
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
        'requested_model': requested_model, 'reported_model': data.get('model'),
        'answer': content, 'finish_reason': choice.get('finish_reason'),
        'truncated': choice.get('finish_reason') == 'length',
        'elapsed_seconds': round(time.monotonic() - started, 2), 'usage': data.get('usage'),
    }


def select_model(inventory: list[dict], model: str | None = None, device: str | None = None,
                 context_length: int = 8192, task_hint: str = 'general',
                 max_load_bytes: int | None = None) -> tuple[str, dict]:
    """Deterministic selection from a fresh, native installed-model inventory."""
    candidates = []
    for row in inventory:
        if not row.get('online') or (device is not None and row.get('device') != device):
            continue
        for item in row.get('models', []):
            if item.get('type') != 'llm' or (model is not None and item.get('key') != model):
                continue
            limit = item.get('max_context_length')
            if isinstance(limit, int) and limit < context_length:
                continue
            if max_load_bytes is not None and not item['loaded_instances'] and (
                not isinstance(item.get('size_bytes'), int) or item['size_bytes'] > max_load_bytes
            ):
                continue
            candidates.append((row['device'], item))
    if not candidates:
        raise ValueError('No suitable installed chat model on an online configured device; no download was made')
    def rank(row):
        target, item = row
        loaded = bool(item['loaded_instances'])
        size = item.get('size_bytes') if isinstance(item.get('size_bytes'), int) else 1 << 62
        capacity = item.get('max_context_length') if isinstance(item.get('max_context_length'), int) else 0
        code_hint = any(term in item['key'].lower() for term in ('code', 'coder', 'devstral'))
        if task_hint == 'code':
            return (not code_hint, not loaded, -capacity, size, target, item['key'])
        if task_hint == 'fast':
            return (not loaded, size, target, item['key'])
        if task_hint == 'long_context':
            return (-capacity, not loaded, size, target, item['key'])
        if task_hint == 'analysis':
            return (not loaded, -capacity, -size, target, item['key'])
        return (not loaded, size, target, item['key'])
    return min(candidates, key=rank)


@contextlib.contextmanager
def inference_lock(device: str | None = None, wait_seconds: float = 0):
    # Per-device queues allow independent configured devices to run concurrently.
    # Router calls have a separate lock because their final host is unknown.
    if device is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', device):
        raise ValueError('Invalid device ID for lock')
    folder = user_cache_path('codex-pair-bridge', appauthor=False)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = FileLock(str(folder / ('router.lock' if device is None else 'device-' + device + '.lock')),
                    timeout=wait_seconds)
    try:
        lock.acquire()
    except Timeout as exc:
        raise ValueError('Another Codex PAIR request is running on this target. Wait for it to finish before calling again.') from exc
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
            return {'device': device, 'online': True, 'checked_at': datetime.now(timezone.utc).isoformat(),
                    'models': checked_models(device, management.models(c)), 'source': 'LM Studio native API'}
    return {'endpoint': BASE_URL, 'models': catalog(), 'notice': 'Catalog only; model availability must be confirmed by a successful request.'}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
@diagnostics.traced
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
    diagnostics.stage('queue', device=device, model=model)
    with inference_lock(device):
        start = time.monotonic()
        diagnostics.stage('inventory')
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
                diagnostics.stage('inference')
                data = management.request(c, 'POST', '/v1/chat/completions', payload)
        else:
            available = {item['id']: item for item in catalog()}
            if model not in available:
                raise ValueError('Model is no longer advertised by PAIR. Refresh pair_list and use an exact ID.')
            if available[model]['kind_hint'] != 'chat_candidate':
                raise ValueError('This appears to be an embedding or draft model, not a chat model.')
            diagnostics.stage('inference')
            data = request('POST', '/chat/completions', payload)
        diagnostics.stage('validation')
        return completion(data, model, device, start)



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
                result.append({'device': name, 'online': True,
                               'checked_at': datetime.now(timezone.utc).isoformat(),
                               'models': checked_models(name, management.models(c))})
        except ValueError as exc:
            result.append({'device': name, 'online': False,
                           'checked_at': datetime.now(timezone.utc).isoformat(),
                           'check_status': 'unreachable', 'error': str(exc)})
    return {'devices': result, 'notice': 'Management covers configured LM Studio devices only. PAIR routing catalog remains pair_list().'}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
def pair_load(device: str, model: str,
              context_length: Annotated[int, Field(ge=512, le=262144)] = 8192) -> dict:
    """Load an installed model on one device into RAM/VRAM; never download weights.

    Reuses existing loaded instances without changing their configuration. May
    consume substantial memory or trigger engine auto-eviction. Verify the result.
    """
    with inference_lock(device), management.client(device) as c:
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
    with inference_lock(device), management.client(device) as c:
        before = management.models(c)
        if not any(i['id'] == instance_id for m in before for i in m['loaded_instances']):
            raise ValueError('Instance is not loaded. Refresh pair_list(device=...)')
        management.request(c, 'POST', '/api/v1/models/unload', {'instance_id': instance_id})
        remaining = management.models(c)
        still_loaded = any(i['id'] == instance_id for m in remaining for i in m['loaded_instances'])
        return {'device': device, 'instance_id': instance_id, 'status': 'not_confirmed' if still_loaded else 'unloaded'}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
@diagnostics.traced
def pair_smart_ask(
    prompt: Annotated[str, Field(min_length=1, max_length=48000)],
    model: str | None = None,
    device: str | None = None,
    context_length: Annotated[int, Field(ge=512, le=262144)] = 8192,
    max_tokens: Annotated[int, Field(ge=32, le=8192)] = 2048,
    unload_after: bool = True,
    task_hint: Annotated[str, Field(pattern='^(general|code|fast|long_context|analysis)$')] = 'general',
    max_load_bytes: Annotated[int | None, Field(ge=1)] = None,
) -> dict:
    """Select an installed LLM from live device inventories, load if needed, ask once, and clean up only a newly created instance.

    No model downloads or silent fallback. Existing loaded instances are preserved.
    An ambiguous multi-instance model is not selected automatically.
    """
    if not prompt.strip():
        raise ValueError('prompt must not be blank')
    diagnostics.stage('inventory', device=device, model=model)
    try:
        router_models = {row['id'] for row in catalog()}
        router_status = 'online'
    except ValueError:
        router_models = set()
        router_status = 'unavailable'
    snapshot = pair_devices()
    selected_device, selected = select_model(snapshot['devices'], model, device, context_length,
                                             task_hint, max_load_bytes)
    diagnostics.stage('queue', device=selected_device, model=selected['key'])
    with inference_lock(selected_device, wait_seconds=30):
        key = selected['key']
        started = time.monotonic()
        owned_id = None
        cleanup = 'not_needed'
        with management.client(selected_device) as c:
            # Recheck after selection: another application may have changed the load state.
            live = management.find_model(c, key)
            if live.get('type') != 'llm':
                raise ValueError('Selected model is no longer a chat LLM; refresh inventory')
            limit = live.get('max_context_length')
            if isinstance(limit, int) and limit < context_length:
                raise ValueError('Selected model context is now smaller than requested; refresh inventory')
            instances = live['loaded_instances']
            if len(instances) > 1:
                raise ValueError('Multiple instances of the selected model are loaded; choose and manage one explicitly')
            if instances:
                load_config = instances[0].get('config')
                actual_context = load_config.get('context_length') if isinstance(load_config, dict) else None
                if isinstance(actual_context, int) and actual_context < context_length:
                    raise ValueError('Loaded instance context is smaller than requested; choose a smaller context or another model')
            if not instances:
                diagnostics.stage('load')
                load_result = management.request(c, 'POST', '/api/v1/models/load', {'model': key, 'context_length': context_length})
                loaded_id = load_result.get('instance_id')
                if not isinstance(loaded_id, str) or not loaded_id:
                    raise ValueError('Load response had no instance ID; inspect state before retrying')
                after = management.find_model(c, key)
                if len(after['loaded_instances']) != 1 or after['loaded_instances'][0]['id'] != loaded_id:
                    raise ValueError('Load state is not confirmed; inspect pair_list before retrying')
                owned_id = loaded_id
                instances = after['loaded_instances']
            payload = {'model': instances[0]['id'], 'messages': [{'role': 'user', 'content': prompt}],
                       'max_tokens': max_tokens, 'stream': False}
            try:
                diagnostics.stage('inference')
                data = management.request(c, 'POST', '/v1/chat/completions', payload)
                diagnostics.stage('validation')
                result = completion(data, key, selected_device, started)
            except Exception:
                # A timeout may leave inference running. Retain the instance for inspection.
                raise
            else:
                if owned_id and unload_after:
                    diagnostics.stage('cleanup')
                    # This lock excludes other bridge calls, but cannot observe external clients.
                    current = management.find_model(c, key)['loaded_instances']
                    if len(current) == 1 and current[0]['id'] == owned_id:
                        try:
                            management.request(c, 'POST', '/api/v1/models/unload', {'instance_id': owned_id})
                            confirmed = management.find_model(c, key)['loaded_instances']
                            cleanup = 'unloaded' if not confirmed else 'not_confirmed'
                        except ValueError:
                            cleanup = 'failed_inspect_instance'
                    else:
                        cleanup = 'state_changed_preserved'
                elif owned_id:
                    cleanup = 'new_instance_retained'
                else:
                    cleanup = 'existing_instance_preserved'
                return dict(result, selected_model=key, instance_id=instances[0]['id'],
                            loaded_for_request=bool(owned_id), cleanup=cleanup,
                            selection_profile=task_hint,
                            selection_reason=('explicit model/device' if model or device else
                                              'installed chat model ranked by profile, load state, context and size'),
                            router_status=router_status, router_advertises_model=key in router_models)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
def pair_compare(prompt: Annotated[str, Field(min_length=1, max_length=48000)],
                 first_model: str, first_device: str, second_model: str, second_device: str,
                 max_tokens: Annotated[int, Field(ge=32, le=8192)] = 2048) -> dict:
    """Ask two explicitly named installed models sequentially; preserve both answers for Codex to assess."""
    if first_model == second_model and first_device == second_device:
        raise ValueError('Comparison requires two distinct model/device targets')
    answers = []
    for model, device in ((first_model, first_device), (second_model, second_device)):
        try:
            answers.append(pair_smart_ask(prompt, model=model, device=device, max_tokens=max_tokens))
        except ValueError as exc:
            answers.append({'device': device, 'model': model, 'error': str(exc)})
    observations = []
    for result in answers:
        if 'answer' not in result:
            observations.append([])
            continue
        observations.append([line.strip().lstrip('-*0123456789. ') for line in result['answer'].splitlines()
                             if len(line.strip()) >= 12][:20])
    shared, disputed = [], []
    if len(observations) == 2:
        used = set()
        for line in observations[0]:
            match = next((i for i, other in enumerate(observations[1]) if i not in used and
                          difflib.SequenceMatcher(None, line.casefold(), other.casefold()).ratio() >= .82), None)
            if match is None:
                disputed.append({'source': 'first', 'observation': line})
            else:
                used.add(match)
                shared.append({'first': line, 'second': observations[1][match]})
        disputed.extend({'source': 'second', 'observation': line} for i, line in enumerate(observations[1]) if i not in used)
    return {'results': answers, 'shared_observations': shared, 'disputed_observations': disputed,
            'verification_status': 'requires_codex_source_review',
            'notice': 'Similarity is textual only. Codex must inspect source files and validate disputed claims before reporting them as findings.'}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def pair_diagnose() -> dict:
    """Read-only device and router health snapshot without prompts, tokens or private URLs."""
    rows = []
    for name in management.devices():
        try:
            with management.client(name) as c:
                models = management.models(c)
            rows.append({'device': name, 'online': True, 'installed': len(models),
                         'chat_models': sum(m.get('type') == 'llm' for m in models),
                         'loaded_instances': sum(len(m['loaded_instances']) for m in models)})
        except ValueError as exc:
            rows.append({'device': name, 'online': False, 'error': str(exc)})
    try:
        advertised = len(catalog())
        router = {'online': True, 'advertised_models': advertised}
    except ValueError:
        router = {'online': False, 'error': 'PAIR router unavailable or catalog invalid'}
    recent = diagnostics.recent()
    explanations = {'timeout': 'The device did not finish before the request deadline; inspect its load state before retrying.',
                    'device_unreachable': 'The device engine could not be reached; check its server and SSH/Tailscale path.',
                    'model_not_installed': 'The requested model is not installed on an online configured device.',
                    'empty_answer': 'The model returned no final text; a larger output budget may be needed.',
                    'load_failed': 'Loading did not complete or could not be confirmed; inspect memory and engine state.',
                    'request_failed': 'The request failed; check local engine logs without sharing prompts or tokens.'}
    return {'devices': rows, 'router': router, 'recent_requests': [dict(row, explanation=explanations.get(row.get('reason')))
                                                                  for row in recent]}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def pair_download_plan(device: str, model: str, estimated_size_bytes: Annotated[int, Field(ge=1)],
                       destination: str, quantization: str | None = None) -> dict:
    """Prepare a one-use download review. Size and destination are caller supplied, not verified by LM Studio.

    LM Studio's download API reveals total size only after starting. Inspect the model
    source, expected size and configured storage location independently before planning.
    """
    if not model or len(model) > 512 or not destination.strip() or len(destination) > 1024:
        raise ValueError('Provide an exact model ID and reviewed destination')
    if quantization is not None and not re.fullmatch(r'[A-Za-z0-9_.-]{1,32}', quantization):
        raise ValueError('Invalid quantization')
    if model.startswith('https://'):
        parts = urlsplit(model)
        if parts.hostname != 'huggingface.co' or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Only exact huggingface.co HTTPS links are accepted as model URLs')
        source = model
    elif re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', model):
        source = 'LM Studio catalog: ' + model
    else:
        raise ValueError('Use an exact LM Studio catalog ID or huggingface.co model URL')
    if device not in management.devices():
        raise ValueError('Unknown device. Use pair_devices and an exact configured ID')
    plan_id = uuid.uuid4().hex
    _DOWNLOAD_PLANS[plan_id] = {'device': device, 'model': model, 'quantization': quantization,
                                'estimated_size_bytes': estimated_size_bytes,
                                'destination': destination, 'created': time.monotonic()}
    return {'plan_id': plan_id, 'device': device, 'model': model, 'source': source,
            'estimated_disk_and_network_bytes': estimated_size_bytes,
            'destination': destination, 'quantization': quantization,
            'notice': 'Estimate and destination are caller supplied and unverified. Review free space and LM Studio storage settings before starting. Plan expires in 10 minutes.'}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
def pair_download(plan_id: str, confirm_model: str) -> dict:
    """Start a download from one reviewed plan, with the exact model ID repeated explicitly."""
    plan = _DOWNLOAD_PLANS.get(plan_id)
    if not plan or time.monotonic() - plan['created'] > 600:
        raise ValueError('Download plan is missing or expired; prepare a new plan')
    if plan['model'] != confirm_model:
        raise ValueError('Repeat the exact model ID in confirm_model before starting a download')
    del _DOWNLOAD_PLANS[plan_id]
    device, model, quantization = plan['device'], plan['model'], plan['quantization']
    with management.client(device) as c:
        body = {'model': model}
        if quantization:
            body['quantization'] = quantization
        result = management.request(c, 'POST', '/api/v1/models/download', body)
    return {'device': device, 'model': model, 'job_id': result.get('job_id'),
            'status': result.get('status'), 'total_size_bytes': result.get('total_size_bytes')}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False))
def pair_download_status(device: str, job_id: str) -> dict:
    """Read the progress of an explicitly started LM Studio download job."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', job_id):
        raise ValueError('Invalid download job ID')
    with management.client(device) as c:
        result = management.request(c, 'GET', '/api/v1/models/download/status/' + job_id)
    return {'device': device, 'job_id': job_id, **{k: result[k] for k in
            ('status', 'total_size_bytes', 'downloaded_bytes', 'bytes_per_second', 'estimated_completion') if k in result}}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
def pair_decide(state: Annotated[str, Field(min_length=1, max_length=48000)],
                instructions: Annotated[str, Field(min_length=1, max_length=1000)],
                criteria: dict[str, str], allow_external: bool = False) -> dict:
    """Ask optional cloud Jev for one typed Choice decision, only with explicit external-send opt-in.

    This is not a chat model and is never an implicit fallback for pair_ask.
    The state is sent to TypeSafe AI, not to local PAIR devices.
    """
    return jev.decide(state, instructions, criteria, allow_external=allow_external)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
def pair_score(state: Annotated[str, Field(min_length=1, max_length=48000)],
               instructions: Annotated[str, Field(min_length=1, max_length=1000)],
               levels: list[str], allow_external: bool = False) -> dict:
    """Ask external TypeSafe AI Jev to score a bounded state on ordered rubric levels.

    Requires explicit allow_external=true; never invoked by local model routing.
    """
    return jev.score(state, instructions, levels, allow_external=allow_external)


if __name__ == '__main__':
    import sys
    if '--self-test' in sys.argv:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent), pattern='test_*.py')
        sys.exit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
    else:
        mcp.run(transport='stdio')
