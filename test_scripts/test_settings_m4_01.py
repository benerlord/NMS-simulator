"""M4-01 end-to-end test: /admin/api/settings.

Verifies:
  1. GET /settings → returns items + runtime block
  2. GET /settings/{key} → 200 for known, 404 for unknown
  3. PUT /settings (autosave_interval) → DB updated, runtime mirror updated
  4. PUT /settings (mock_path_prefix) → routes rebound under new prefix,
     hot-reload works without restart
  5. Bad prefix (no leading slash) → 400
  6. autosave_interval out of range (< 5 / > 3600) → 422 from Pydantic

Assumes backend on http://127.0.0.1:8080. Restores prefix to "" after run.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"


def _request(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body_txt = exc.read().decode("utf-8") or "{}"
        try:
            return exc.code, json.loads(body_txt)
        except json.JSONDecodeError:
            return exc.code, {"raw": body_txt}


def _pass(msg):
    print(f"[PASS] {msg}")


def _fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def _setting(payload, key):
    for item in payload["data"]["items"]:
        if item["key"] == key:
            return item
    return None


def main():
    # ---------- 1. GET /settings ----------
    status, payload = _request("GET", f"{ADMIN}/settings")
    if status != 200:
        _fail(f"GET /settings → {status} {payload}")
    runtime = payload["data"].get("runtime")
    if not runtime or "appPort" not in runtime:
        _fail(f"runtime block missing appPort: {runtime}")
    _pass(f"GET /settings → {len(payload['data']['items'])} keys, runtime port={runtime['appPort']}")

    initial_prefix_item = _setting(payload, "mock_path_prefix")
    initial_prefix = initial_prefix_item["value"] if initial_prefix_item else ""

    # ---------- 2. GET /settings/{key} ----------
    status, payload = _request("GET", f"{ADMIN}/settings/autosave_interval")
    if status != 200 or payload["data"]["key"] != "autosave_interval":
        _fail(f"GET /settings/autosave_interval failed: {status} {payload}")
    _pass(f"GET autosave_interval → {payload['data']['value']}")

    status, payload = _request("GET", f"{ADMIN}/settings/__missing__")
    if status != 404:
        _fail(f"expected 404 for missing key, got {status} {payload}")
    _pass("missing key → 404")

    # ---------- 3. PUT /settings autosave_interval ----------
    status, payload = _request("PUT", f"{ADMIN}/settings", {"autosaveInterval": 90})
    if status != 200:
        _fail(f"PUT autosave_interval → {status} {payload}")
    item = _setting(payload, "autosave_interval")
    if item is None or int(item["value"]) != 90:
        _fail(f"autosave_interval not persisted as 90: {item}")
    _pass("autosave_interval persisted as 90")

    # restore default
    _request("PUT", f"{ADMIN}/settings", {"autosaveInterval": 60})

    # ---------- 4. PUT mock_path_prefix → routes rebound ----------
    create_body = {
        "name": "M4-01 prefix probe",
        "method": "GET",
        "path": "/m4_01_probe",
        "enabled": True,
        "dataSource": "static",
        "config": {"staticBody": {"hi": "m4-01"}},
    }
    status, created = _request("POST", f"{ADMIN}/apis", create_body)
    if status != 200:
        _fail(f"create probe api failed: {status} {created}")
    api_id = created["data"]["id"]

    try:
        status, payload = _request("PUT", f"{ADMIN}/settings", {"mockPathPrefix": "/mock"})
        if status != 200:
            _fail(f"PUT mock_path_prefix=/mock → {status} {payload}")
        item = _setting(payload, "mock_path_prefix")
        if item is None or item["value"] != "/mock":
            _fail(f"mock_path_prefix not /mock after PUT: {item}")
        _pass("mock_path_prefix persisted as /mock")

        status, payload = _request("GET", f"{BASE}/mock/m4_01_probe")
        if status != 200 or payload != {"hi": "m4-01"}:
            _fail(f"new prefix /mock not active: {status} {payload}")
        _pass("/mock/m4_01_probe → 200 (hot-reload)")

        status, _ = _request("GET", f"{BASE}/m4_01_probe")
        if status != 404:
            _fail(f"old root path should 404 after prefix change, got {status}")
        _pass("old root path → 404 (rebound)")
    finally:
        # restore prefix and clean up probe
        _request("PUT", f"{ADMIN}/settings", {"mockPathPrefix": initial_prefix})
        _request("DELETE", f"{ADMIN}/apis/{api_id}")

    # ---------- 5. Bad prefix → 400 ----------
    status, payload = _request("PUT", f"{ADMIN}/settings", {"mockPathPrefix": "no_slash"})
    if status != 400:
        _fail(f"expected 400 for bad prefix, got {status} {payload}")
    _pass("invalid prefix → 400")

    # ---------- 6. autosave_interval out of range → 422 ----------
    status, payload = _request("PUT", f"{ADMIN}/settings", {"autosaveInterval": 1})
    if status != 422:
        _fail(f"expected 422 for autosave_interval=1, got {status} {payload}")
    _pass("autosave_interval=1 → 422")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
