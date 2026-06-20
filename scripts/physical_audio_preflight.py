#!/usr/bin/env python3
"""Read-only preflight for physical Jarvis audio loopback testing."""

from __future__ import annotations

import json
import subprocess
from typing import Any


LOOPBACK_NAME_MARKERS = (
    "blackhole",
    "loopback",
    "soundflower",
    "vb-cable",
    "virtual cable",
    "background music",
)


def physical_audio_preflight() -> dict[str, Any]:
    """Return whether this Mac appears ready for no-human physical audio-loop QA.

    The check only reads CoreAudio metadata through system_profiler. It does not
    open the microphone, capture speaker output, change the default audio
    device, or request macOS permissions.
    """
    try:
        completed = subprocess.run(
            ["system_profiler", "SPAudioDataType", "-json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "ok": False,
            "status": "system_profiler_unavailable",
            "error": f"{type(error).__name__}: {error}",
            "requests_microphone": False,
            "captures_audio": False,
        }
    if completed.returncode != 0:
        return {
            "ok": False,
            "status": "system_profiler_failed",
            "error": (completed.stderr or completed.stdout).strip()[-1000:],
            "requests_microphone": False,
            "captures_audio": False,
        }
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as error:
        return {
            "ok": False,
            "status": "invalid_system_profiler_json",
            "error": str(error),
            "requests_microphone": False,
            "captures_audio": False,
        }
    devices = audio_devices_from_system_profiler(payload)
    loopback_devices = [device for device in devices if is_loopback_candidate(device)]
    virtual_duplex_devices = [
        device
        for device in devices
        if is_virtual_duplex_candidate(device) and not is_loopback_candidate(device)
    ]
    input_devices = [device for device in devices if device.get("input_channels", 0) > 0]
    output_devices = [device for device in devices if device.get("output_channels", 0) > 0]
    ready = bool(loopback_devices)
    return {
        "ok": True,
        "status": "loopback_ready" if ready else "loopback_device_missing",
        "ready_for_physical_capture": ready,
        "loopback_devices": loopback_devices,
        "virtual_duplex_devices": virtual_duplex_devices,
        "input_device_count": len(input_devices),
        "output_device_count": len(output_devices),
        "device_names": [str(device.get("name") or "") for device in devices],
        "requests_microphone": False,
        "captures_audio": False,
        "note": (
            "A virtual loopback audio device is visible; a future explicit physical loop can route Jarvis speech into STT."
            if ready
            else "No obvious loopback audio device is visible, so physical speaker/microphone proof still fails closed."
        ),
    }


def audio_devices_from_system_profiler(payload: dict[str, Any]) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    groups = payload.get("SPAudioDataType")
    if not isinstance(groups, list):
        return devices
    for group in groups:
        if not isinstance(group, dict):
            continue
        items = group.get("_items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("_name") or "").strip()
            if not name:
                continue
            devices.append({
                "name": name,
                "manufacturer": str(item.get("coreaudio_device_manufacturer") or ""),
                "transport": str(item.get("coreaudio_device_transport") or ""),
                "input_channels": int(item.get("coreaudio_device_input") or 0),
                "output_channels": int(item.get("coreaudio_device_output") or 0),
                "default_input": str(item.get("coreaudio_default_audio_input_device") or "") == "spaudio_yes",
                "default_output": str(item.get("coreaudio_default_audio_output_device") or "") == "spaudio_yes",
                "default_system_output": str(item.get("coreaudio_default_audio_system_device") or "") == "spaudio_yes",
            })
    return devices


def is_loopback_candidate(device: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(device.get(key) or "")
        for key in ("name", "manufacturer", "transport")
    ).casefold()
    if not any(marker in haystack for marker in LOOPBACK_NAME_MARKERS):
        return False
    return bool(device.get("input_channels", 0) > 0 and device.get("output_channels", 0) > 0)


def is_virtual_duplex_candidate(device: dict[str, Any]) -> bool:
    transport = str(device.get("transport") or "").casefold()
    return (
        "virtual" in transport
        and bool(device.get("input_channels", 0) > 0)
        and bool(device.get("output_channels", 0) > 0)
    )


def main() -> int:
    result = physical_audio_preflight()
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
