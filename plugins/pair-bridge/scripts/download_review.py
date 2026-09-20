"""Read-only checks for an explicit LM Studio download plan."""
from pathlib import Path
import shutil
from urllib.parse import urlsplit

import httpx


def model_files(model, quantization):
    """Return one exact GGUF file size from public Hugging Face metadata, if unambiguous."""
    parts = urlsplit(model)
    if parts.scheme != 'https' or parts.hostname != 'huggingface.co':
        return {'status': 'unavailable', 'reason': 'Catalog ID has no proven Hugging Face repository mapping'}
    path = parts.path.strip('/').split('/')
    if len(path) != 2 or not all(path):
        return {'status': 'unavailable', 'reason': 'Use an exact Hugging Face repository URL'}
    repo = '/'.join(path)
    try:
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
            response = client.get('https://huggingface.co/api/models/' + repo, params={'blobs': 'true'})
            response.raise_for_status()
            info = response.json()
    except (httpx.HTTPError, ValueError):
        return {'status': 'unavailable', 'reason': 'Hugging Face metadata could not be read'}
    if not isinstance(info, dict) or not isinstance(info.get('siblings'), list):
        return {'status': 'unavailable', 'reason': 'Hugging Face file metadata is incomplete'}
    files = []
    for item in info['siblings']:
        if not isinstance(item, dict) or not isinstance(item.get('rfilename'), str):
            continue
        name = item['rfilename']
        if not name.lower().endswith('.gguf'):
            continue
        if quantization and quantization.lower() not in name.lower():
            continue
        size = item.get('size')
        if not isinstance(size, int) and isinstance(item.get('lfs'), dict):
            size = item['lfs'].get('size')
        if isinstance(size, int) and size > 0:
            files.append({'name': name, 'size_bytes': size})
    if len(files) != 1:
        return {'status': 'ambiguous', 'matching_files': files[:20],
                'reason': 'Expected one GGUF file with known size; choose an exact quantization or inspect a sharded model manually'}
    return {'status': 'verified_file', 'repository': repo, 'revision': info.get('sha'),
            'file': files[0]['name'], 'size_bytes': files[0]['size_bytes'],
            'note': 'This is one repository file, not a guarantee of the LM Studio download job total.'}


def destination_space(device, destination, required_bytes):
    """Inspect disk free space only when the target device is the local host."""
    origin = urlsplit(device.get('base_url', ''))
    if device.get('ssh_host') or origin.hostname not in ('127.0.0.1', 'localhost'):
        return {'status': 'unknown', 'reason': 'Remote storage path and free space are not exposed by LM Studio API'}
    path = Path(destination).expanduser()
    if not path.is_absolute():
        return {'status': 'unknown', 'reason': 'Destination must be an absolute local path to inspect free space'}
    parent = path
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    try:
        free = shutil.disk_usage(parent).free
    except OSError:
        return {'status': 'unknown', 'reason': 'Cannot inspect destination filesystem'}
    return {'status': 'enough' if free >= required_bytes else 'insufficient',
            'free_bytes': free, 'required_bytes': required_bytes,
            'note': 'The path is caller supplied; LM Studio does not confirm it as its configured model directory.'}
