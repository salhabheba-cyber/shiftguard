import json
import urllib.request
import urllib.error

API_BASE = "https://api.nextdns.io"


def _request(method, path, api_key, body=None):
    req = urllib.request.Request(API_BASE + path, method=method)
    req.add_header('X-Api-Key', api_key)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, data=data, timeout=8) as resp:
            raw = resp.read()
            return True, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
            detail = err.get('errors', [{}])[0].get('detail')
        except Exception:
            detail = None
        return False, detail or f'NextDNS returned HTTP {e.code}'
    except Exception as e:
        return False, str(e)


def test_connection(api_key, profile_id):
    """Verify the API key + profile ID are valid. Returns (ok, message)."""
    if not api_key or not profile_id:
        return False, "API key and Profile ID are required"
    ok, data = _request('GET', f'/profiles/{profile_id}', api_key)
    if not ok:
        return False, data
    name = (data.get('data') or {}).get('name') or profile_id
    return True, f'Connected to NextDNS profile "{name}"'


def add_domain(api_key, profile_id, domain):
    return _request('POST', f'/profiles/{profile_id}/denylist', api_key, {'id': domain})


def remove_domain(api_key, profile_id, domain):
    return _request('DELETE', f'/profiles/{profile_id}/denylist/{domain}', api_key)


def get_denylist(api_key, profile_id):
    ok, data = _request('GET', f'/profiles/{profile_id}/denylist', api_key)
    if not ok:
        return []
    return [d['id'] for d in data.get('data', []) if 'id' in d]


def sync_all(api_key, profile_id, domains):
    """Push every domain in `domains` to the NextDNS denylist (skips ones already there)."""
    existing = set(get_denylist(api_key, profile_id))
    added, failed = 0, []
    for domain in domains:
        if domain in existing:
            continue
        ok, err = add_domain(api_key, profile_id, domain)
        if ok:
            added += 1
        else:
            failed.append(domain)
    return added, failed
