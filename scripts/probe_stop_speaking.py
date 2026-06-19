#!/usr/bin/env python3
"""Quietly verify Jarvis stop-speaking behavior against a live worker."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.render_overnight_status import normalize_base_url  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--command", default="stop talking")
    args = parser.parse_args(argv)

    try:
        result = probe_stop_speaking(args.base_url, command=args.command)
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def probe_stop_speaking(base_url: str, *, command: str = "stop talking") -> dict[str, Any]:
    base_url = normalize_base_url(base_url)
    response = post_json(
        f"{base_url}/api/command",
        {"command": command, "suppress_speech": True},
        timeout=15.0,
    )
    result_payload = response.get("result") if isinstance(response.get("result"), dict) else {}
    speech_payload = response.get("speech")
    failures: list[str] = []

    if response.get("tool") != "voice.stop_speaking":
        failures.append(f"expected voice.stop_speaking tool, got {response.get('tool')!r}")
    if response.get("executed") is not True:
        failures.append("stop-speaking command did not execute")
    if speech_payload is not None:
        failures.append("stop-speaking command unexpectedly returned a speech payload")
    if result_payload.get("started_audio") is True or result_payload.get("played_audio") is True:
        failures.append("stop-speaking command reported starting or playing audio")

    result_reply = str(result_payload.get("reply") or "").strip()
    summary = str(response.get("summary") or "").strip()
    if result_reply and summary != result_reply:
        failures.append("visible summary does not match the stop-speaking tool reply")
    if not result_reply and summary not in {"I was not speaking.", "Stopped speaking.", "Stopped Jarvis speech playback."}:
        failures.append(f"unexpected stop-speaking summary: {summary!r}")

    return {
        "ok": not failures,
        "tool": response.get("tool"),
        "summary": summary,
        "result_status": result_payload.get("status"),
        "result_reply": result_reply,
        "speech": speech_payload,
        "failures": failures,
    }


def post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error


if __name__ == "__main__":
    raise SystemExit(main())
