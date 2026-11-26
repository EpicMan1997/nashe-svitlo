"""One-time, read-only check of the two models requested by the owner."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from ecoflow_probe import DEVICE_LIST, DEVICE_QUOTA, ProbeError, extract_devices, request_api, safe_model

TARGETS = ("DELTA 3 Plus", "RIVER 3 Plus")

def safe_error(exc):
    match = re.search(r"(?:code |HTTP error )(\d{1,7})", str(exc))
    return match.group(1) if match else "unavailable"

def audit(access, secret):
    if not access or not secret:
        return {"list_status": "missing_credentials", "models": {}}
    try:
        devices = extract_devices(request_api(DEVICE_LIST, access, secret))
    except ProbeError as exc:
        return {"list_status": "error", "code": safe_error(exc), "models": {}}
    results = {}
    for model in TARGETS:
        matched = [d for d in devices if isinstance(d, dict) and safe_model(d) == model]
        if not matched:
            results[model] = {"status": "not_listed"}
            continue
        if len(matched) != 1 or not isinstance(matched[0].get("sn"), str) or not matched[0]["sn"]:
            results[model] = {"status": "ambiguous"}
            continue
        try:
            quota = request_api(DEVICE_QUOTA, access, secret, {"sn": matched[0]["sn"]})
            results[model] = {"status": "quota_available" if isinstance(quota, dict) and quota else "empty"}
        except ProbeError as exc:
            code = safe_error(exc)
            results[model] = {"status": "denied" if code == "1006" else "error", "code": code}
    return {"list_status": "ok", "models": results}

if __name__ == "__main__":
    report = audit(os.getenv("ECOFLOW_ACCESS_KEY", "").strip(), os.getenv("ECOFLOW_SECRET_KEY", "").strip())
    report["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Only generic model names, status codes and timestamps. No serials, secrets, or telemetry.
    path = Path(__file__).resolve().parents[1] / "state" / "ecoflow_compatibility.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ECOFLOW_COMPATIBILITY", json.dumps(report, ensure_ascii=False))
