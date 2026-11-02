#!/usr/bin/env python3
"""Read-only EcoFlow API connectivity probe. Never prints credentials or serials.

Run manually via .github/workflows/ecoflow-probe.yml. This script does not store,
send to third parties, or publish any data. Only GET requests to the EU API.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api-e.ecoflow.com"
DEVICE_LIST = "/iot-open/sign/device/list"
DEVICE_QUOTA = "/iot-open/sign/device/quota/all"
MAX_QUOTA_CHECKS = 15
# No custom device names or partial serials leave the probe.
MODELS = (
    ("DELTA PRO 3", "DELTA Pro 3"),
    ("DELTA 3 PLUS", "DELTA 3 Plus"),
    ("DELTA 2 MAX", "DELTA 2 Max"),
    ("DELTA 2", "DELTA 2"),
    ("RIVER 3 PLUS", "RIVER 3 Plus"),
    ("RIVER 3", "RIVER 3"),
    ("RIVER 2", "RIVER 2"),
    ("POWEROCEAN", "PowerOcean"),
    ("POWER OCEAN", "PowerOcean"),
)


class ProbeError(Exception):
    pass


def signed_headers(access_key, secret_key, query=None, *, nonce=None, timestamp=None):
    """EcoFlow HMAC-SHA256 canonical query, sorted by ASCII key name."""
    nonce = str(nonce if nonce is not None else secrets.randbelow(900000) + 100000)
    timestamp = str(timestamp if timestamp is not None else int(time.time() * 1000))
    data = {"accessKey": access_key, "nonce": nonce, "timestamp": timestamp}
    items = {**data, **(query or {})}
    sign_string = "&".join(f"{key}={items[key]}" for key in sorted(items))
    signature = hmac.new(secret_key.encode("utf-8"), sign_string.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    return {**data, "sign": signature}


def request_api(path, access_key, secret_key, query=None):
    if path not in (DEVICE_LIST, DEVICE_QUOTA):
        raise ProbeError("Blocked endpoint")
    params = query or {}
    headers = signed_headers(access_key, secret_key, params)
    url = API + path + ("?" + urlencode(params) if params else "")
    # Explicit GET: this diagnostic never sends EcoFlow settings or commands.
    req = Request(url, method="GET", headers=headers)
    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read(2_000_000).decode("utf-8"))
    except HTTPError as exc:
        raise ProbeError(f"EcoFlow HTTP error {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("Could not reach EcoFlow EU API") from None
    except (ValueError, UnicodeError):
        raise ProbeError("EcoFlow returned an invalid JSON response") from None

    if not isinstance(payload, dict):
        raise ProbeError("EcoFlow returned an unexpected response type")
    code = payload.get("code", 0)
    if str(code) not in ("0", "200"):
        # Do not log raw messages: API errors can reflect request parameters.
        cleaned = str(code) if re.fullmatch(r"\d{1,7}", str(code)) else "unavailable"
        raise ProbeError(f"EcoFlow rejected request (code {cleaned})")
    return payload.get("data")


def safe_model(record):
    candidates = [record.get("productName"), record.get("productType"),
                  record.get("deviceName"), record.get("name")]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        normalized = re.sub(r"\s+", " ", candidate.upper().replace("-", " ").replace("_", " "))
        for needle, model in MODELS:
            if needle in normalized:
                return model
    return "Модель не визначена"


def online_status(value):
    if value is True or value in (1, "1", "online", "ONLINE"):
        return "online"
    if value is False or value in (0, "0", "offline", "OFFLINE"):
        return "offline"
    return "unknown"


def extract_devices(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("list", "devices", "deviceList", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ProbeError("Device list response has an unexpected structure")


def main():
    access = os.environ.get("ECOFLOW_ACCESS_KEY", "").strip()
    secret = os.environ.get("ECOFLOW_SECRET_KEY", "").strip()
    if not access or not secret:
        raise ProbeError("Add ECOFLOW_ACCESS_KEY and ECOFLOW_SECRET_KEY in repository Actions secrets")
    print("EcoFlow EU read-only connectivity test")
    devices = extract_devices(request_api(DEVICE_LIST, access, secret))
    print(f"Devices visible to API: {len(devices)}")
    if not devices:
        print("No bound devices found. Verify the EcoFlow mobile app uses the same account.")
        return
    for i, item in enumerate(devices, start=1):
        if not isinstance(item, dict):
            raise ProbeError("Unexpected device entry type")
        print(f"  #{i}: {safe_model(item)} | {online_status(item.get('online'))}")
    print("Device names, serial numbers and credentials are deliberately hidden.")
    checked = success = 0
    for item in devices[:MAX_QUOTA_CHECKS]:
        sn = item.get("sn") if isinstance(item, dict) else None
        if not isinstance(sn, str) or not sn:
            continue
        checked += 1
        try:
            quota = request_api(DEVICE_QUOTA, access, secret, {"sn": sn})
            if isinstance(quota, dict) and quota:
                success += 1
        except ProbeError:
            continue
    print(f"Read-only quota available: {success}/{checked} checked devices.")
    if success == 0:
        print("No quota fields received. Device support or API permissions need investigation.")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as exc:
        print(f"EcoFlow probe failed: {exc}", file=sys.stderr)
        sys.exit(1)
