#!/usr/bin/env python3
"""One-time read-only probe of EcoFlow official Developer MQTT.

Logs only device indices and counters. Does not emit MQTT messages or
publish serials, topics, credentials or payload values.
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

from ecoflow_probe import (
    API, DEVICE_LIST, ProbeError, extract_devices,
    request_api, safe_model, signed_headers
)

TOPIC_WAIT_SECONDS = 18


def certificate(access, secret, sn):
    path = "/iot-open/sign/certification"
    query = {"sn": sn}
    req = urllib.request.Request(
        API + path + "?" + urllib.parse.urlencode(query),
        headers=signed_headers(access, secret, query),
        method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            payload = json.loads(response.read(100000))
    except Exception:
        return None, "certificate-request-failed"
    if not isinstance(payload, dict):
        return None, "certificate-response-invalid"
    code = str(payload.get("code", ""))
    if code not in ("0", "200"):
        return None, ("api-error-" + code if re.fullmatch(r"\d{1,7}", code) else "api-error")
    result = payload.get("data")
    if not isinstance(result, dict):
        return None, "no-certificate-data"
    return result, "ok"


def main():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise ProbeError("paho-mqtt dependency is unavailable")
    access = os.environ.get("ECOFLOW_ACCESS_KEY", "")
    secret = os.environ.get("ECOFLOW_SECRET_KEY", "")
    if not access or not secret:
        raise ProbeError("Developer API secrets are missing")
    devices = extract_devices(request_api(DEVICE_LIST, access, secret))
    print(f"Developer MQTT diagnostic: {len(devices)} discovered devices")
    certs = []
    for i, d in enumerate(devices):
        if not isinstance(d, dict) or not isinstance(d.get("sn"), str):
            print(f"#{i+1} unknown: no serial from authorized device list")
            continue
        cert, outcome = certificate(access, secret, d["sn"])
        print(f"#{i+1} {safe_model(d)}: MQTT credentials {outcome}")
        if cert:
            certs.append((i, cert))
    if not certs:
        print("No MQTT certificates issued. No MQTT connection attempted.")
        return

    i, credential = certs[0]
    raw_host = credential.get("url")
    user = credential.get("certificateAccount")
    password = credential.get("certificatePassword")
    port = credential.get("port")
    if not isinstance(raw_host, str) or not isinstance(user, str) or not isinstance(password, str):
        print("MQTT certificate incomplete; no connection attempted.")
        return
    parsed = urllib.parse.urlparse(raw_host if "://" in raw_host else "//" + raw_host)
    host = parsed.hostname
    try:
        port = int(port)
    except (ValueError, TypeError):
        print("MQTT port missing")
        return
    # TLS only. Do not send the user/password over a plain MQTT socket.
    if not host or port not in (8883, 8884, 443):
        print("MQTT endpoint is not on an approved TLS port; skipped safely.")
        return
    index_by_topic = {}
    for i, item in enumerate(devices):
        sn = item.get("sn") if isinstance(item, dict) else None
        if isinstance(sn, str) and sn:
            index_by_topic[f"/open/{user}/{sn}/quota"] = i + 1

    counts = Counter()
    subacks = Counter()
    connection = {"code": None}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="nashe_svitlo_diag_" + str(os.getpid()))
    client.username_pw_set(user, password)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.tls_insecure_set(False)

    def on_connect(c, userdata, flags, reason_code, properties):
        connection["code"] = str(reason_code)
        if reason_code == 0:
            for topic in index_by_topic:
                c.subscribe(topic, qos=0)

    def on_subscribe(c, userdata, mid, reason_codes, properties):
        for reason in reason_codes:
            subacks[str(reason)] += 1

    def on_message(c, userdata, msg):
        # Never deserialize MQTT payload or print sensitive topic/serial data.
        idx = index_by_topic.get(msg.topic)
        if idx is not None:
            counts[idx] += 1

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    try:
        client.connect(host, port, keepalive=30)
        client.loop_start()
        time.sleep(TOPIC_WAIT_SECONDS)
    except Exception:
        print("MQTT TLS connection failed; no credentials/details logged.")
    finally:
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass
    print(f"MQTT TLS session state: {connection['code'] or 'unconfirmed'}")
    print("Subscription acknowledgements:", dict(subacks))
    for i, item in enumerate(devices, 1):
        print(f"#{i} {safe_model(item)}: {counts[i]} push frames in {TOPIC_WAIT_SECONDS}s")
    print("No commands were sent, and no MQTT payloads or credentials were logged.")
    print("Zero messages is inconclusive: the device may have been idle or the topic restricted.")


if __name__ == "__main__":
    try:
        main()
    except ProbeError as err:
        print("Probe error: " + str(err), file=sys.stderr)
        sys.exit(1)
