#!/usr/bin/env python3
"""One-time binding of DELTA 2 serials to locations, without persisting serials.

Uses owner-observed SOC as a *one-time* identification check. Once bound,
a keyed HMAC fingerprint persists and is independent of future SOC changes.
Do not rerun for remapping. This workflow never exposes raw identifiers.
"""
import hmac
import hashlib
import itertools
import json
import os
from pathlib import Path
from ecoflow_probe import DEVICE_LIST, DEVICE_QUOTA, ProbeError, extract_devices, request_api, safe_model
from ecoflow_live_normalize import nested_get, read_number

ROOT = Path(__file__).resolve().parents[1]
BINDINGS = ROOT / "state" / "ecoflow_bindings.json"
TARGETS = {"dacha:d2": 98, "solovky:d2": 80, "naumenky:d2": 92}
HMAC_CONTEXT = b"nashe-svitlo/ecoflow-device-key/v1:"


def fingerprint(serial, secret):
    return hmac.new(secret.encode(), HMAC_CONTEXT + serial.encode(), hashlib.sha256).hexdigest()


def eligible(entry):
    return isinstance(entry, dict) and safe_model(entry) == "DELTA 2" and isinstance(entry.get("sn"), str)


def read_devices(access, secret):
    result = []
    devices = extract_devices(request_api(DEVICE_LIST, access, secret))
    for item in devices:
        if not eligible(item):
            continue
        quota = request_api(DEVICE_QUOTA, access, secret, {"sn": item["sn"]})
        if not isinstance(quota, dict):
            raise ProbeError("A DELTA 2 returned an unexpected quota response")
        soc = read_number(nested_get(quota, "pd.soc"), "socPercent")
        addon = read_number(nested_get(quota, "bms_slave.soc"), "socPercent")
        result.append({"serial": item["sn"], "soc": soc, "addon": addon})
    return result, devices


def matching(readings):
    if len(readings) != 3 or any(d["soc"] is None for d in readings):
        raise ValueError("Need exactly three readable DELTA 2 devices")
    print("One-time observations (in developer device-list order):")
    for i, d in enumerate(readings, 1):
        print(f"  DELTA 2 #{i}: {d['soc']:.1f}% | extra pack: "
              + (f"{d['addon']:.1f}%" if d["addon"] is not None else "not reported"))
    candidates = []
    keys = list(TARGETS)
    for order in itertools.permutations(range(len(readings))):
        deviations = [abs(readings[index]["soc"] - TARGETS[key]) for key, index in zip(keys, order)]
        if all(x <= 5 for x in deviations):
            candidates.append((sum(deviations), order))
    candidates.sort(key=lambda row: row[0])
    if not candidates or (len(candidates) > 1 and
                          candidates[1][0] - candidates[0][0] < 3):
        raise ValueError("Current SOC values do not uniquely match 98/80/92 within 5 points; not binding")
    order = candidates[0][1]
    result = {key: readings[index] for key, index in zip(keys, order)}
    if result["solovky:d2"]["addon"] is None:
        raise ValueError("Solovky's DELTA 2 has no readable extra-battery SOC; not binding")
    print("Owner-verified location association matches unique readings.")
    return result


def main():
    access = os.environ.get("ECOFLOW_ACCESS_KEY", "")
    secret = os.environ.get("ECOFLOW_SECRET_KEY", "")
    if not access or not secret:
        raise ValueError("Missing EcoFlow GitHub Actions secrets")
    if BINDINGS.exists():
        print("Existing private-keyed bindings already exist; nothing overwritten.")
        return
    readings, devices = read_devices(access, secret)
    assignments = matching(readings)
    bindings = {
        "version": 1,
        "type": "hmac-sha256",
        "devices": {
            key: fingerprint(reading["serial"], secret)
            for key, reading in assignments.items()
        },
    }
    BINDINGS.parent.mkdir(parents=True, exist_ok=True)
    BINDINGS.write_text(json.dumps(bindings, indent=2) + "\n", encoding="utf-8")
    print("Wrote stable private-keyed identities for: " + ", ".join(TARGETS))
    print("No serials, access keys, secret keys, private device labels or raw quotas persisted.")
    for item in devices:
        if not isinstance(item, dict) or safe_model(item) != "DELTA Pro 3":
            continue
        try:
            quota = request_api(DEVICE_QUOTA, access, secret, {"sn": item["sn"]})
        except ProbeError:
            continue
        print("DELTA Pro 3 BMS field comparison (system vs internal battery):")
        for field in ("cmsBattSoc", "bmsBattSoc", "cmsBattFullEnergy",
                      "bmsDesignCap", "plugInInfo4p81InFlag",
                      "plugInInfo4p82InFlag", "plugInInfo4p82Detail"):
            value = nested_get(quota, field) if isinstance(quota, dict) else None
            if isinstance(value, (int, float, bool)) and not isinstance(value, str):
                print(f"  {field}: {value}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, ProbeError) as exc:
        print(f"DELTA 2 binding stopped safely: {exc}")
        raise SystemExit(1)
