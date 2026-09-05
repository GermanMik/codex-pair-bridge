"""Device-scoped LM Studio management; never starts a second PAIR broker."""
import contextlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.parse import urlsplit
import httpx


def devices():
    path = Path.home() / '.codex-pair-bridge.json'
    config = json.loads(path.read_text()) if path.exists() else {}
    rows = config.get('devices', [])
    if not isinstance(rows, list):
        raise ValueError('devices must be a list')
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Each device must be an object')
        name = row.get('id', '')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name) or name in result:
            raise ValueError('Device IDs must be unique short names')
        url = row.get('base_url', '')
        p = urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
            raise ValueError('Device base_url must be an HTTP(S) origin without credentials')
        if row.get('engine', 'lmstudio') != 'lmstudio':
            raise ValueError('This version supports LM Studio management only')
        host = row.get('ssh_host')
        if host is not None and (not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', host)):
            raise ValueError('ssh_host must be an existing SSH config alias')
        if host and (p.scheme != 'http' or p.hostname not in ('localhost', '127.0.0.1')):
            raise ValueError('SSH devices must target the remote HTTP loopback origin')
        key = row.get('api_key_env')
        if key is not None and (not isinstance(key, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key)):
            raise ValueError('api_key_env must name an environment variable')
        result[name] = dict(row, base_url=url.rstrip('/'))
    return result


@contextlib.contextmanager
def endpoint(device):
    if not device.get('ssh_host'):
        yield device['base_url']
        return
    p = urlsplit(device['base_url'])
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    # SSH configuration supplies authentication. No remote shell is invoked.
    args = ['ssh', '-N', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=10',
            '-L', f'127.0.0.1:{port}:127.0.0.1:{p.port or 80}', device['ssh_host']]
    try:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise ValueError('SSH is unavailable; install OpenSSH and configure the device alias') from exc
    try:
        deadline = time.monotonic() + 12
        while True:
            if process.poll() is not None:
                raise ValueError('SSH tunnel failed. Check the existing host alias, host key, and authentication')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError('SSH tunnel startup timed out')
                time.sleep(.05)
        yield f'http://127.0.0.1:{port}'
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@contextlib.contextmanager
def client(device_id):
    all_devices = devices()
    if device_id not in all_devices:
        raise ValueError('Unknown device. Use pair_devices and an exact configured ID')
    device = all_devices[device_id]
    key_env = device.get('api_key_env')
    key = os.environ.get(key_env) if key_env else None
    if key_env and not key:
        raise ValueError('Configured device API token environment variable is missing')
    with endpoint(device) as url:
        with httpx.Client(base_url=url, timeout=180, trust_env=False, follow_redirects=False,
                          headers={'Authorization': 'Bearer ' + key} if key else {}) as c:
            yield c


def request(c, method, route, body=None):
    try:
        r = c.request(method, route, json=body)
    except httpx.TimeoutException as exc:
        raise ValueError('Device timed out; operation may still be running. Inspect status before retrying') from exc
    except httpx.RequestError as exc:
        raise ValueError('Device engine is unreachable') from exc
    if not r.is_success:
        raise ValueError(f'Device returned HTTP {r.status_code}; no retry was made')
    try:
        data = r.json()
    except ValueError as exc:
        raise ValueError('Device returned invalid JSON') from exc
    if not isinstance(data, dict) or 'error' in data:
        raise ValueError('Device returned an error or invalid response')
    return data


def models(c):
    rows = request(c, 'GET', '/api/v1/models').get('models')
    if not isinstance(rows, list):
        raise ValueError('LM Studio native v1 API is required')
    out = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('key'), str) or not isinstance(row.get('loaded_instances'), list):
            raise ValueError('Invalid model inventory; cannot determine loaded state')
        instances = row['loaded_instances']
        if any(not isinstance(x, dict) or not isinstance(x.get('id'), str) for x in instances):
            raise ValueError('Invalid loaded instance inventory')
        out.append({k: row[k] for k in ('key', 'display_name', 'type', 'size_bytes', 'max_context_length', 'loaded_instances') if k in row})
    return out


def find_model(c, key):
    rows = [m for m in models(c) if m['key'] == key]
    if len(rows) != 1:
        raise ValueError('Model is not installed on this device. Refresh pair_list(device=...); no download was made')
    return rows[0]
