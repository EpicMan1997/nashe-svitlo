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
        "dacha:dp3": "unavailable",
        "dacha:dp3eb": "unavailable",
        "dacha:d3p": "unsupported",
        "dacha:d2": "unavailable" if bindings else "unassigned",
        "dacha:r3pw": "unsupported",
        "home:po": "unsupported",
        "solovky:d2": "unavailable" if bindings else "unassigned",
        "solovky:d2eb": "unavailable",
        "solovky:r2": "unsupported",
        "naumenky:d2": "unavailable" if bindings else "unassigned",
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
    for device in api_devices:
        if not isinstance(device, dict):
            continue
        model, serial = safe_model(device), device.get("sn")
        if not isinstance(serial, str) or not serial:
            continue
        if model == "DELTA Pro 3" and dp3_count == 1:
            key, kind = "dacha:dp3", "delta_pro_3"
        elif model == "DELTA 2":
            key = canonical_delta2(serial, secret, bindings) if bindings else None
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
        try:
            quota = request_api(DEVICE_QUOTA, access, secret, {"sn": serial})
        except ProbeError:
            continue
        if not isinstance(quota, dict):
            continue
        reading = fresh_reading(quota, key, kind, now.timestamp())
        if reading is None:
            continue

        if key == "dacha:dp3":
            # CMS reports the combined SOC of both 4096 Wh packs. BMS reports
            # the physical main battery SOC. The EB SOC is not exposed directly
            # in the approved field inventory, so its SOC is labelled estimated.
            combined = read_number(nested_get(quota, "cmsBattSoc"), "socPercent")
            primary = read_number(nested_get(quota, "bmsBattSoc"), "socPercent")
            total_capacity = nested_get(quota, "cmsBattFullEnergy")
            if primary is not None:
                reading["socPercent"] = round(primary, 1)
            elif combined is not None:
                reading["socPercent"] = round(combined, 1)
                reading["estimated"] = True  # System rather than physical main SOC
            else:
                reading.pop("socPercent", None)
            result["devices"][key] = reading
            availability[key] = "readable"
            if (combined is not None and primary is not None and
                isinstance(total_capacity, (int, float)) and not isinstance(total_capacity, bool) and
                abs(total_capacity - 8192) <= 50):
                # Equal battery nominal Wh allows a linear *approximation* only.
                inferred = 2 * combined - primary
                if 0 <= inferred <= 100:
                    result["devices"]["dacha:dp3eb"] = {
                        "updatedAt": reading["updatedAt"],
                        "socPercent": round(inferred, 1),
                        "estimated": True,
                        "operation": "unknown",
                    }
                    availability["dacha:dp3eb"] = "readable"
            continue

        # Each DELTA 2 returns its own main physical battery SOC.
        primary = read_number(nested_get(quota, "bms_bmsStatus.soc"), "socPercent")
        if primary is not None:
            reading["socPercent"] = round(primary, 1)
        result["devices"][key] = reading
        if key in availability:
            availability[key] = "readable"

        # Owner confirmed that only Solovky DELTA 2 has a 1024 Wh extra pack.
        # Other units may expose a stale bms_slave field, which is not proof
        # of a physically attached battery.
        if key == "solovky:d2":
            addon = read_number(nested_get(quota, "bms_slave.soc"), "socPercent")
            if addon is not None:
                result["devices"]["solovky:d2eb"] = {
                    "updatedAt": reading["updatedAt"],
                    "socPercent": round(addon, 1),
                    "operation": "unknown",
                }
                availability["solovky:d2eb"] = "readable"
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
        except Exception:
            # Outage publishing must stay independent of upstream EcoFlow access.
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
