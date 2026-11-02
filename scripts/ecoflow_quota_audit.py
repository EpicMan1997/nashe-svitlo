#!/usr/bin/env python3
"""Audit EcoFlow device quotas without exposing serials, user labels or values.

This is a one-shot read-only test. No credentials, personal strings, raw
telemetry or serial numbers are written to logs or repository files.
"""
import os
import re
import sys

from ecoflow_probe import (
    DEVICE_LIST, DEVICE_QUOTA, MAX_QUOTA_CHECKS, ProbeError,
    extract_devices, online_status, request_api, safe_model
)

SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
PRIVATE = re.compile(
    r"(?i)(?:^|[._-])(sn|serial|deviceid|uuid|mac|ipaddr|ip|imei|ssid|"
    r"wifi|network|user|owner|name|account|email|phone|auth|cert|secret|"
    r"password|pwd|token|longitude|latitude|address|location|geo|key)(?:$|[._-])"
    r"|(?i:serialnum|macaddr|deviceuuid|username|useremail|device_name)"
)
MAX_FIELDS_PRINTED = 450


def safe_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return f"array({len(value)})"
    return "object"


def scan_keys(data):
    """Only list safe field *names* and their primitive types, never values."""
    found = {}
    def scan(value, prefix="", depth=0):
        if depth > 8 or len(found) > 4000:
            return
        if isinstance(value, dict):
            for key, nested in value.items():
                if not isinstance(key, str) or not SAFE_NAME.fullmatch(key):
                    continue
                full = f"{prefix}.{key}" if prefix else key
                if PRIVATE.search(full):
                    continue
                if isinstance(nested, dict):
                    scan(nested, full, depth + 1)
                elif isinstance(nested, list):
                    found[full] = safe_type(nested)
                    if nested and isinstance(nested[0], dict):
                        scan(nested[0], full + "[]", depth + 1)
                else:
                    found[full] = safe_type(nested)
    scan(data)
    return found


def category(name):
    key = name.lower()
    for label, patterns in (
        ("Charge, SOC, BMS", ("soc", "bms", "battery", "bat", "charge", "remain", "capacity", "soh", "cycle")),
        ("Electrical power & energy", ("watt", "power", "watts", "energy", "pwr", "input", "output", "grid", "inverter", "inv", "ac", "dc", "solar", "pv", "eps", "mppt", "load", "phase")),
        ("Voltage, current & frequency", ("volt", "current", "amp", "freq", "hz", "ma")),
        ("Thermal & hardware", ("temp", "fan", "heat", "error", "fault", "warn", "relay")),
        ("Modes & config feedback", ("mode", "cfg", "setting", "reserve", "limit", "switch", "enable", "state", "type", "time", "status", "version")),
    ):
        if any(term in key for term in patterns):
            return label
    return "Other"


def public_product_code(item):
    """Allow only short coded device classes, never custom labels or SN prefixes."""
    for key in ("productType", "deviceType", "productModel"):
        val = item.get(key)
        if isinstance(val, str) and re.fullmatch(r"[A-Za-z]{2,12}(?:[-_][A-Za-z]{2,10})?", val):
            return val
    return None


def main():
    access = os.environ.get("ECOFLOW_ACCESS_KEY", "").strip()
    secret = os.environ.get("ECOFLOW_SECRET_KEY", "").strip()
    if not access or not secret:
        raise ProbeError("Missing EcoFlow GitHub Actions secrets")
    devices = extract_devices(request_api(DEVICE_LIST, access, secret))
    print(f"=== ECOFLOW QUOTA FIELD AUDIT: {len(devices)} DEVICES ===")
    print("Values, serials, API credentials and custom device names are never logged.")
    for i, item in enumerate(devices[:MAX_QUOTA_CHECKS], 1):
        if not isinstance(item, dict):
            print(f"DEVICE #{i}: invalid listing")
            continue
        model = safe_model(item)
        product_code = public_product_code(item)
        product_suffix = f" | productType: {product_code}" if product_code else ""
        online = online_status(item.get("online"))
        print(f"\nDEVICE #{i}: {model} | {online}{product_suffix}")
        sn = item.get("sn")
        if not isinstance(sn, str) or not sn:
            print("QUOTA: NOT TESTED (no serial in response)")
            continue
        try:
            data = request_api(DEVICE_QUOTA, access, secret, {"sn": sn})
        except ProbeError as exc:
            print(f"QUOTA: ERROR ({str(exc)})")
            continue
        if not isinstance(data, dict):
            print(f"QUOTA: NO DICTIONARY (type={safe_type(data)})")
            continue
        fields = scan_keys(data)
        if not fields:
            print(f"QUOTA: EMPTY/NO SAFE FIELDS (returned {len(data)} root keys)")
            continue
        print(f"QUOTA: OK | {len(fields)} safe flattened fields | {len(data)} root keys")
        groups = {}
        for key, typ in sorted(fields.items(), key=lambda it: it[0].lower()):
            groups.setdefault(category(key), []).append((key, typ))
        for title, items in groups.items():
            print(f"  {title} ({len(items)}):")
            for key, typ in items[:MAX_FIELDS_PRINTED]:
                print(f"    {key} [{typ}]")
            if len(items) > MAX_FIELDS_PRINTED:
                print(f"    ... {len(items)-MAX_FIELDS_PRINTED} more keys omitted")
    print("\nAudit complete. No write command sent.")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as e:
        print(f"Audit failed: {e}", file=sys.stderr)
        sys.exit(1)
