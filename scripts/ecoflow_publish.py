#!/usr/bin/env python3
"""Publish read-only EcoFlow snapshots for GitHub Pages.

Verified DELTA 2 locations are bound by keyed HMAC identities, independent
of current SOC and API list order. No secret, serial, user name or raw quota
may be exposed. Unavailable values stay absent, never turn into demo values.
"""
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from ecoflow_probe import (
    DEVICE_LIST, DEVICE_QUOTA, ProbeError, extract_devices, request_api, safe_model
)
from ecoflow_live_normalize import StationReading, nested_get, read_number
from ecoflow_bind_delta2 import BINDINGS, TARGETS, fingerprint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "ecoflow-snapshot.json"
UNASSIGNED = ("unassigned:delta2-1", "unassigned:delta2-2", "unassigned:delta2-3")


def load_bindings():
    if not BINDINGS.is_file():
        return {}
    raw = json.loads(BINDINGS.read_text(encoding="utf-8"))
    if raw.get("version") != 1 or raw.get("type") != "hmac-sha256":
        raise ValueError("Unsupported EcoFlow binding format")
    devices = raw.get("devices", {})
    if not isinstance(devices, dict) or set(devices) != set(TARGETS):
        raise ValueError("Incomplete EcoFlow device bindings")
    fingerprints = list(devices.values())
    if any(not isinstance(fp, str) or not re.fullmatch(r"[0-9a-f]{64}", fp)
           for fp in fingerprints) or len(set(fingerprints)) != len(fingerprints):
        raise ValueError("Invalid or repeated EcoFlow binding fingerprint")
    return devices


def canonical_delta2(serial, secret, bindings):
    fp = fingerprint(serial, secret)
    for key, target in bindings.items():
        if hmac.compare_digest(fp, target):
            return key
    return None


def public_error_status(error):
    """Only sanitized error categories leave this process; never log SN or URL."""
    code = str(error)
    return "rate_limited" if ("429" in code or "quota" in code.lower()) else "api_error"


def public_error_code(error):
    """Return only a numeric HTTP/API code or safe category, never raw text."""
    if not isinstance(error, ProbeError):
        return "unexpected"
    message = str(error)
    found = re.search(r"(?:HTTP error|code)\s+(\d{3,7})", message)
    if found:
        return "code_" + found.group(1)
    if "Could not reach" in message:
        return "network"
    if "invalid JSON" in message:
        return "invalid_json"
    if "response type" in message:
        return "invalid_response"
    return "unknown"


def fresh_reading(quota, key, model, timestamp):
    # Existing normalizer validates numbers and never mistakes 0 for missing.
    typekey = "dacha:dp3" if model == "delta_pro_3" else "dacha:d2"
    station = StationReading(typekey, model)
    if not station.update(quota, timestamp):
        return None
    return station.snapshot(timestamp)


def build_snapshot(access, secret, now=None, bindings=None):
    now = now or datetime.now(timezone.utc)
    generated = now.isoformat(timespec="seconds")
    if bindings is None:
        bindings = load_bindings()
    availability = {
        "dacha:dp3": "not_listed",
        "dacha:dp3eb": "unavailable",
        "dacha:d3p": "unsupported",
        "dacha:d2": "not_listed" if bindings else "unassigned",
        "dacha:r3pw": "unsupported",
        "home:po": "unsupported",
        "solovky:d2": "not_listed" if bindings else "unassigned",
        "solovky:d2eb": "unavailable",
        "solovky:r2": "unsupported",
        "naumenky:d2": "not_listed" if bindings else "unassigned",
    }
    result = {
        "version": 1, "emittedAt": generated, "mode": "scheduled",
        "devices": {}, "availability": availability,
        "unassigned": [], "connection": "ok",
    }
    api_devices = extract_devices(request_api(DEVICE_LIST, access, secret))
    dp3_count = sum(safe_model(d) == "DELTA Pro 3"
                    for d in api_devices if isinstance(d, dict))
    seen = set()
    unassigned_index = 0
    diag = {"delta2_listed": 0, "delta2_bound": 0,
            "quota_limited": 0, "quota_failed": 0, "invalid_data": 0,
            "codes": {}}
    for device in api_devices:
        if not isinstance(device, dict):
            continue
        model, serial = safe_model(device), device.get("sn")
        if not isinstance(serial, str) or not serial:
            continue
        if model == "DELTA Pro 3" and dp3_count == 1:
            key, kind = "dacha:dp3", "delta_pro_3"
        elif model == "DELTA 2":
            diag["delta2_listed"] += 1
            key = canonical_delta2(serial, secret, bindings) if bindings else None
            if key is not None:
                diag["delta2_bound"] += 1
            if key is None:
                if unassigned_index >= len(UNASSIGNED):
                    continue
                key = UNASSIGNED[unassigned_index]
                unassigned_index += 1
                result["unassigned"].append(key)
            kind = "delta_2"
        else:
            continue
        if key in seen:
            # Duplicates must not silently override or cross-map other stations.
            result["devices"].pop(key, None)
            if key in availability:
                availability[key] = "unavailable"
            continue
        seen.add(key)
        # Seen in the authenticated list, but data may be rejected independently.
        if key in availability:
            availability[key] = "api_error"
        try:
            quota = request_api(DEVICE_QUOTA, access, secret, {"sn": serial})
        except ProbeError as error:
            reason = public_error_status(error)
            error_code = public_error_code(error)
            diag["codes"][error_code] = diag["codes"].get(error_code, 0) + 1
            diag["quota_limited" if reason == "rate_limited" else "quota_failed"] += 1
            if key in availability:
                availability[key] = reason
            continue
        if not isinstance(quota, dict):
            diag["invalid_data"] += 1
            if key in availability:
                availability[key] = "invalid_data"
            continue
        reading = fresh_reading(quota, key, kind, now.timestamp())
        if reading is None or reading.get("socPercent") is None:
            diag["invalid_data"] += 1
            if key in availability:
                availability[key] = "invalid_data"
            continue

        if key == "dacha:dp3":
            # EcoFlow CMS SOC already covers the complete 8192 Wh system.
            # Never infer or publish separate main/extra battery percentages.
            combined = read_number(nested_get(quota, "cmsBattSoc"), "socPercent")
            if combined is None:
                reading.pop("socPercent", None)
            else:
                reading["socPercent"] = round(combined, 1)
            result["devices"][key] = reading
            availability[key] = "readable"
            continue

        # pd.soc is the station-reported combined SOC. On Solovky this one
        # value belongs to the complete 2048 Wh station + expansion system.
        combined = read_number(nested_get(quota, "pd.soc"), "socPercent")
        if combined is None:
            reading.pop("socPercent", None)
        else:
            reading["socPercent"] = round(combined, 1)
        result["devices"][key] = reading
        if key in availability:
            availability[key] = "readable"
    # Explicit counts make transient failures diagnosable without exposing
    # serials, device IDs from EcoFlow, credentials or raw quota responses.
    print("EcoFlow quota diagnostics: DELTA2 listed=" +
          str(diag["delta2_listed"]) +
          ", matched=" + str(diag["delta2_bound"]) +
          ", rate-limited=" + str(diag["quota_limited"]) +
          ", failed=" + str(diag["quota_failed"]) +
          ", invalid=" + str(diag["invalid_data"]) +
          ", error_codes=" + ",".join(
              f"{code}:{count}" for code, count in sorted(diag["codes"].items())))
    return result


def main():
    access = os.getenv("ECOFLOW_ACCESS_KEY", "").strip()
    secret = os.getenv("ECOFLOW_SECRET_KEY", "").strip()
    if not access or not secret:
        state = {
            "version": 1, "mode": "scheduled",
            "emittedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "devices": {}, "unassigned": [], "connection": "unavailable",
        }
    else:
        try:
            state = build_snapshot(access, secret)
        except Exception as error:
            # Outage publishing must stay independent of upstream EcoFlow access.
            # Sanitized category only: never print API URLs, serials or secrets.
            print("EcoFlow provider error: " +
                  ((public_error_status(error) + " / " + public_error_code(error))
                   if isinstance(error, ProbeError) else "unavailable"))
            state = {
                "version": 1, "mode": "scheduled",
                "emittedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "devices": {}, "unassigned": [], "connection": "unavailable",
            }
    OUT.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    print("EcoFlow snapshot: " + str(len(state["devices"])) +
          " readable battery/station entries, " + str(len(state["unassigned"])) +
          " unassigned DELTA 2, provider " + state["connection"])


if __name__ == "__main__":
    main()
