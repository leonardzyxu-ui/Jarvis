#!/usr/bin/env python3
"""Generate a numbered Jarvis TTS audition set and ranking page."""

from __future__ import annotations

import argparse
import html
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "runtime" / "tts_voice_audition"
DEFAULT_SAMPLE_TEXT = (
    "Good evening, Leo. I've checked your email: there's a short form about the "
    "charity sale that may need your attention. I'll keep it brief unless you ask for more."
)
SEED = "jarvis-tts-audition-2026-06-05"
EDGE_CA_CERT = Path("/opt/homebrew/Cellar/ca-certificates/2025-05-20/share/ca-certificates/cacert.pem")


@dataclass(frozen=True)
class Candidate:
    provider: str
    voice: str
    label: str
    accent: str
    style: str
    rate: int = 152
    edge_rate: str = "+0%"
    edge_pitch: str = "+0Hz"
    priority: int = 0


MACOS_CANDIDATES = [
    Candidate("macos_say", "Daniel", "macOS Daniel", "English UK", "classic male system voice", priority=90),
    Candidate("macos_say", "Eddy (English (UK))", "macOS Eddy UK", "English UK", "newer Apple voice", priority=92),
    Candidate("macos_say", "Reed (English (UK))", "macOS Reed UK", "English UK", "newer Apple voice", priority=91),
    Candidate("macos_say", "Rocko (English (UK))", "macOS Rocko UK", "English UK", "newer Apple voice", priority=86),
    Candidate("macos_say", "Sandy (English (UK))", "macOS Sandy UK", "English UK", "newer Apple voice", priority=86),
    Candidate("macos_say", "Shelley (English (UK))", "macOS Shelley UK", "English UK", "newer Apple voice", priority=84),
    Candidate("macos_say", "Flo (English (UK))", "macOS Flo UK", "English UK", "newer Apple voice", priority=82),
    Candidate("macos_say", "Grandpa (English (UK))", "macOS Grandpa UK", "English UK", "character voice", priority=70),
    Candidate("macos_say", "Grandma (English (UK))", "macOS Grandma UK", "English UK", "character voice", priority=68),
    Candidate("macos_say", "Samantha", "macOS Samantha", "English US", "natural Apple voice", priority=88),
    Candidate("macos_say", "Moira", "macOS Moira", "English Ireland", "clear system voice", priority=82),
    Candidate("macos_say", "Karen", "macOS Karen", "English Australia", "clear system voice", priority=78),
    Candidate("macos_say", "Tessa", "macOS Tessa", "English South Africa", "clear system voice", priority=76),
    Candidate("macos_say", "Aman", "macOS Aman", "English India", "clear system voice", priority=72),
    Candidate("macos_say", "Rishi", "macOS Rishi", "English India", "clear system voice", priority=72),
    Candidate("macos_say", "Albert", "macOS Albert", "English US", "older male system voice", priority=55),
    Candidate("macos_say", "Fred", "macOS Fred", "English US", "older male system voice", priority=54),
    Candidate("macos_say", "Ralph", "macOS Ralph", "English US", "older male system voice", priority=50),
    Candidate("macos_say", "Kathy", "macOS Kathy", "English US", "older female system voice", priority=50),
]


EDGE_CANDIDATES = [
    Candidate("edge_tts", "en-GB-ThomasNeural", "Edge Thomas Neural", "English UK", "male general neural", priority=100),
    Candidate("edge_tts", "en-GB-RyanNeural", "Edge Ryan Neural", "English UK", "male general neural", priority=99),
    Candidate("edge_tts", "en-GB-SoniaNeural", "Edge Sonia Neural", "English UK", "female general neural", priority=96),
    Candidate("edge_tts", "en-GB-LibbyNeural", "Edge Libby Neural", "English UK", "female general neural", priority=94),
    Candidate("edge_tts", "en-GB-MaisieNeural", "Edge Maisie Neural", "English UK", "female general neural", priority=88),
    Candidate("edge_tts", "en-IE-ConnorNeural", "Edge Connor Neural", "English Ireland", "male general neural", priority=90),
    Candidate("edge_tts", "en-IE-EmilyNeural", "Edge Emily Neural", "English Ireland", "female general neural", priority=86),
    Candidate("edge_tts", "en-AU-WilliamMultilingualNeural", "Edge William Multilingual", "English Australia", "male multilingual neural", priority=84),
    Candidate("edge_tts", "en-AU-NatashaNeural", "Edge Natasha Neural", "English Australia", "female general neural", priority=78),
    Candidate("edge_tts", "en-CA-LiamNeural", "Edge Liam Neural", "English Canada", "male general neural", priority=78),
    Candidate("edge_tts", "en-CA-ClaraNeural", "Edge Clara Neural", "English Canada", "female general neural", priority=74),
    Candidate("edge_tts", "en-ZA-LukeNeural", "Edge Luke Neural", "English South Africa", "male general neural", priority=76),
    Candidate("edge_tts", "en-ZA-LeahNeural", "Edge Leah Neural", "English South Africa", "female general neural", priority=72),
    Candidate("edge_tts", "en-US-AndrewMultilingualNeural", "Edge Andrew Multilingual", "English US", "warm confident conversational", priority=90),
    Candidate("edge_tts", "en-US-AndrewNeural", "Edge Andrew Neural", "English US", "warm confident conversational", priority=88),
    Candidate("edge_tts", "en-US-BrianMultilingualNeural", "Edge Brian Multilingual", "English US", "approachable conversational", priority=84),
    Candidate("edge_tts", "en-US-BrianNeural", "Edge Brian Neural", "English US", "approachable conversational", priority=82),
    Candidate("edge_tts", "en-US-AvaMultilingualNeural", "Edge Ava Multilingual", "English US", "expressive conversational", priority=78),
    Candidate("edge_tts", "en-US-EmmaMultilingualNeural", "Edge Emma Multilingual", "English US", "clear conversational", priority=76),
    Candidate("edge_tts", "en-US-ChristopherNeural", "Edge Christopher Neural", "English US", "authoritative news/novel", priority=74),
    Candidate("edge_tts", "en-US-SteffanNeural", "Edge Steffan Neural", "English US", "rational news/novel", priority=72),
    Candidate("edge_tts", "en-US-RogerNeural", "Edge Roger Neural", "English US", "lively news/novel", priority=68),
]


def run(command: list[str], *, timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
        check=False,
    )


def available_macos_voice_names() -> set[str]:
    say = shutil.which("say")
    if not say:
        return set()
    completed = run([say, "-v", "?"], timeout=8)
    if completed.returncode != 0:
        return set()
    names: set[str] = set()
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        marker = "  "
        if marker in line:
            names.add(line.split(marker, 1)[0].strip())
    return names


def edge_command(output_dir: Path) -> Path | None:
    local = output_dir / ".venv" / "bin" / "edge-tts"
    if local.exists():
        return local
    found = shutil.which("edge-tts")
    return Path(found) if found else None


def candidate_pool(output_dir: Path, max_samples: int | None) -> tuple[list[Candidate], list[dict[str, Any]]]:
    unavailable: list[dict[str, Any]] = []
    macos_names = available_macos_voice_names()
    candidates: list[Candidate] = []
    if macos_names:
        for candidate in MACOS_CANDIDATES:
            if candidate.voice in macos_names:
                candidates.append(candidate)
            else:
                unavailable.append({"provider": candidate.provider, "voice": candidate.voice, "reason": "macOS voice is not installed"})
    else:
        unavailable.append({"provider": "macos_say", "voice": "*", "reason": "macOS say is unavailable or did not list voices"})

    if edge_command(output_dir):
        candidates.extend(EDGE_CANDIDATES)
    else:
        for candidate in EDGE_CANDIDATES:
            unavailable.append({"provider": candidate.provider, "voice": candidate.voice, "reason": "edge-tts command is unavailable"})

    ranked = sorted(candidates, key=lambda item: (-item.priority, item.provider, item.voice))
    if max_samples is not None:
        ranked = ranked[:max_samples]

    rng = random.Random(SEED)
    rng.shuffle(ranked)
    return ranked, unavailable


def convert_to_mp3(source: Path, target: Path) -> tuple[bool, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "ffmpeg is not available"
    completed = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-codec:a", "libmp3lame", "-q:a", "2", str(target)], timeout=30)
    if completed.returncode != 0:
        return False, completed.stderr.strip() or "ffmpeg conversion failed"
    return True, ""


def generate_macos(candidate: Candidate, text: str, target: Path) -> tuple[bool, str]:
    say = shutil.which("say")
    if not say:
        return False, "macOS say is unavailable"
    with tempfile.TemporaryDirectory(prefix="jarvis-tts-") as tmp_name:
        tmp = Path(tmp_name) / "sample.aiff"
        completed = run([say, "-v", candidate.voice, "-r", str(candidate.rate), "-o", str(tmp), text], timeout=30)
        if completed.returncode != 0:
            return False, completed.stderr.strip() or "say failed"
        return convert_to_mp3(tmp, target)


def edge_env(output_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    venv_cert = output_dir / ".venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "certifi" / "cacert.pem"
    if venv_cert.exists():
        env.setdefault("SSL_CERT_FILE", str(venv_cert))
    elif EDGE_CA_CERT.exists():
        env.setdefault("SSL_CERT_FILE", str(EDGE_CA_CERT))
    return env


def generate_edge(candidate: Candidate, text: str, target: Path, output_dir: Path) -> tuple[bool, str]:
    command = edge_command(output_dir)
    if not command:
        return False, "edge-tts command is unavailable"
    errors: list[str] = []
    for attempt in range(1, 4):
        completed = run(
            [
                str(command),
                "--voice",
                candidate.voice,
                "--rate",
                candidate.edge_rate,
                "--pitch",
                candidate.edge_pitch,
                "--text",
                text,
                "--write-media",
                str(target),
            ],
            timeout=45,
            env=edge_env(output_dir),
        )
        if completed.returncode == 0 and target.exists() and target.stat().st_size > 1000:
            return True, ""
        errors.append((completed.stderr or completed.stdout or f"attempt {attempt} failed").strip())
        time.sleep(1.5)
    return False, errors[-1] if errors else "edge-tts failed"


def probe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    completed = run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        timeout=8,
    )
    if completed.returncode != 0:
        return None
    try:
        return round(float(completed.stdout.strip()), 3)
    except ValueError:
        return None


def html_page(samples: list[dict[str, Any]], sample_text: str, generated_at: str) -> str:
    samples_json = json.dumps(samples, ensure_ascii=False, indent=2)
    escaped_sentence = html.escape(sample_text)
    escaped_generated_at = html.escape(generated_at)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Jarvis Voice Audition</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --ink: #181b20;
      --muted: #69707d;
      --line: #d9dde5;
      --red: #a4162a;
      --red-dark: #74101d;
      --gold: #c8942e;
      --blue: #1f5f8f;
      --shadow: 0 18px 45px rgba(21, 25, 33, 0.10);
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
      letter-spacing: 0;
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 44px;
    }}
    header {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 20px;
      align-items: end;
      padding: 18px 0 20px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.15;
      font-weight: 760;
    }}
    .sentence {{
      margin: 0;
      max-width: 780px;
      color: var(--muted);
      line-height: 1.55;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }}
    button {{
      appearance: none;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      min-height: 38px;
      padding: 0 12px;
      border-radius: 7px;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
      transition: border-color 140ms ease, background 140ms ease, color 140ms ease, transform 140ms ease;
      white-space: nowrap;
    }}
    button:hover {{
      border-color: #aeb5c2;
      transform: translateY(-1px);
    }}
    button.primary {{
      background: var(--red);
      border-color: var(--red);
      color: white;
    }}
    button.primary:hover {{
      background: var(--red-dark);
      border-color: var(--red-dark);
    }}
    button.gold {{
      border-color: rgba(200, 148, 46, 0.55);
      color: #594019;
      background: #fff8e8;
    }}
    .status {{
      min-height: 22px;
      margin: 14px 0 16px;
      color: var(--blue);
      font-weight: 650;
    }}
    .list {{
      display: grid;
      gap: 10px;
    }}
    .row {{
      display: grid;
      grid-template-columns: 48px 78px 86px 1fr 126px;
      gap: 12px;
      align-items: center;
      min-height: 68px;
      padding: 11px 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 1px 0 rgba(255, 255, 255, 0.85);
    }}
    .row.dragging {{
      opacity: 0.55;
      box-shadow: var(--shadow);
    }}
    .rank {{
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border-radius: 7px;
      background: #eef1f5;
      color: #49515f;
      font-weight: 760;
      font-variant-numeric: tabular-nums;
    }}
    .sample-number {{
      display: grid;
      place-items: center;
      min-width: 56px;
      height: 36px;
      border-radius: 7px;
      background: #181b20;
      color: white;
      font-size: 18px;
      font-weight: 800;
      font-variant-numeric: tabular-nums;
    }}
    .identity {{
      min-width: 0;
    }}
    .identity strong {{
      display: block;
      font-size: 16px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .meta {{
      display: none;
      margin-top: 3px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }}
    body.show-details .meta {{
      display: block;
    }}
    .moves {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }}
    .moves button {{
      min-height: 34px;
      padding: 0 8px;
    }}
    .handle {{
      color: var(--muted);
      font-weight: 700;
      cursor: grab;
    }}
    audio {{
      display: none;
    }}
    footer {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    @media (max-width: 820px) {{
      main {{
        width: min(100% - 20px, 720px);
        padding-top: 12px;
      }}
      header {{
        grid-template-columns: 1fr;
        align-items: start;
      }}
      .toolbar {{
        justify-content: flex-start;
      }}
      .row {{
        grid-template-columns: 42px 68px 78px 1fr;
      }}
      .moves {{
        grid-column: 1 / -1;
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 560px) {{
      .row {{
        grid-template-columns: 42px 68px 1fr;
      }}
      .row > button {{
        grid-column: 1 / 3;
      }}
      .identity {{
        grid-column: 3;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Jarvis Voice Audition</h1>
        <p class="sentence">{escaped_sentence}</p>
      </div>
      <div class="toolbar">
        <button class="primary" id="copy-json">Copy JSON</button>
        <button id="copy-text">Copy Text</button>
        <button id="toggle-details">Show Details</button>
        <button class="gold" id="reset-order">Reset</button>
        <button id="stop-audio">Stop</button>
      </div>
    </header>
    <div class="status" id="status"></div>
    <section class="list" id="list" aria-label="Voice sample ranking"></section>
    <footer>{len(samples)} samples generated at {escaped_generated_at}. The visible number is the only thing you need to rank.</footer>
  </main>
  <script>
    const samples = {samples_json};
    const sampleText = {json.dumps(sample_text)};
    const generatedAt = {json.dumps(generated_at)};
    const storageKey = "jarvis-voice-audition:" + generatedAt + ":" + samples.length;
    const list = document.getElementById("list");
    const status = document.getElementById("status");
    let currentAudio = null;

    function savedOrder() {{
      try {{
        const parsed = JSON.parse(localStorage.getItem(storageKey) || "null");
        if (!Array.isArray(parsed)) return samples.map(sample => sample.number);
        const known = new Set(samples.map(sample => sample.number));
        const filtered = parsed.filter(number => known.has(number));
        const missing = samples.map(sample => sample.number).filter(number => !filtered.includes(number));
        return filtered.concat(missing);
      }} catch {{
        return samples.map(sample => sample.number);
      }}
    }}

    function orderedSamples() {{
      const byNumber = new Map(samples.map(sample => [sample.number, sample]));
      return savedOrder().map(number => byNumber.get(number)).filter(Boolean);
    }}

    function saveOrder() {{
      const numbers = [...list.querySelectorAll(".row")].map(row => Number(row.dataset.number));
      localStorage.setItem(storageKey, JSON.stringify(numbers));
    }}

    function setStatus(message) {{
      status.textContent = message;
      if (message) setTimeout(() => {{
        if (status.textContent === message) status.textContent = "";
      }}, 1800);
    }}

    function stopAudio() {{
      if (currentAudio) {{
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio = null;
      }}
    }}

    function playSample(sample, button) {{
      stopAudio();
      const audio = new Audio(sample.file);
      currentAudio = audio;
      button.textContent = "Playing";
      audio.addEventListener("ended", () => {{
        button.textContent = "Play";
        if (currentAudio === audio) currentAudio = null;
      }});
      audio.addEventListener("error", () => {{
        button.textContent = "Play";
        setStatus("Could not play sample " + sample.number);
      }});
      audio.play().catch(() => {{
        button.textContent = "Play";
        setStatus("Browser blocked playback");
      }});
    }}

    function moveRow(row, direction) {{
      if (direction < 0 && row.previousElementSibling) {{
        list.insertBefore(row, row.previousElementSibling);
      }}
      if (direction > 0 && row.nextElementSibling) {{
        list.insertBefore(row.nextElementSibling, row);
      }}
      refreshRanks();
      saveOrder();
    }}

    function refreshRanks() {{
      [...list.querySelectorAll(".row")].forEach((row, index) => {{
        row.querySelector(".rank").textContent = String(index + 1);
      }});
    }}

    function render() {{
      list.innerHTML = "";
      for (const sample of orderedSamples()) {{
        const row = document.createElement("article");
        row.className = "row";
        row.draggable = true;
        row.dataset.number = sample.number;
        row.innerHTML = `
          <div class="rank"></div>
          <div class="sample-number">${{sample.number}}</div>
          <button type="button" class="play">Play</button>
          <div class="identity">
            <strong>Sample ${{sample.number}}</strong>
            <div class="meta">${{sample.provider}} / ${{sample.voice}} / ${{sample.accent}} / ${{sample.style}}</div>
          </div>
          <div class="moves">
            <button type="button" class="up">Up</button>
            <button type="button" class="down">Down</button>
          </div>
        `;
        row.querySelector(".play").addEventListener("click", event => playSample(sample, event.currentTarget));
        row.querySelector(".up").addEventListener("click", () => moveRow(row, -1));
        row.querySelector(".down").addEventListener("click", () => moveRow(row, 1));
        row.addEventListener("dragstart", event => {{
          row.classList.add("dragging");
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", String(sample.number));
        }});
        row.addEventListener("dragend", () => {{
          row.classList.remove("dragging");
          saveOrder();
          refreshRanks();
        }});
        list.appendChild(row);
      }}
      refreshRanks();
    }}

    list.addEventListener("dragover", event => {{
      event.preventDefault();
      const dragging = list.querySelector(".dragging");
      if (!dragging) return;
      const rows = [...list.querySelectorAll(".row:not(.dragging)")];
      const after = rows.find(row => event.clientY <= row.getBoundingClientRect().top + row.offsetHeight / 2);
      if (after) list.insertBefore(dragging, after);
      else list.appendChild(dragging);
    }});

    function currentNumbers() {{
      return [...list.querySelectorAll(".row")].map(row => Number(row.dataset.number));
    }}

    async function copyText(text, label) {{
      try {{
        await navigator.clipboard.writeText(text);
        setStatus(label + " copied");
      }} catch {{
        const box = document.createElement("textarea");
        box.value = text;
        document.body.appendChild(box);
        box.select();
        document.execCommand("copy");
        box.remove();
        setStatus(label + " copied");
      }}
    }}

    document.getElementById("copy-json").addEventListener("click", () => {{
      const payload = {{
        ranked_sample_numbers: currentNumbers(),
        sample_text: sampleText,
        generated_at: generatedAt
      }};
      copyText(JSON.stringify(payload, null, 2), "JSON");
    }});

    document.getElementById("copy-text").addEventListener("click", () => {{
      copyText(currentNumbers().join(", "), "Text");
    }});

    document.getElementById("toggle-details").addEventListener("click", event => {{
      document.body.classList.toggle("show-details");
      event.currentTarget.textContent = document.body.classList.contains("show-details") ? "Hide Details" : "Show Details";
    }});

    document.getElementById("reset-order").addEventListener("click", () => {{
      localStorage.removeItem(storageKey);
      render();
      setStatus("Order reset");
    }});

    document.getElementById("stop-audio").addEventListener("click", stopAudio);

    render();
  </script>
</body>
</html>
"""


def generate(output_dir: Path, text: str, max_samples: int | None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_dir = output_dir / "samples"
    if samples_dir.exists():
        for old_file in samples_dir.glob("*.mp3"):
            old_file.unlink()
    samples_dir.mkdir(parents=True, exist_ok=True)

    candidates, unavailable = candidate_pool(output_dir, max_samples)
    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    generated: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    next_number = 1
    for candidate in candidates:
        target = samples_dir / f"{next_number}.mp3"
        started = time.monotonic()
        if candidate.provider == "macos_say":
            ok, error = generate_macos(candidate, text, target)
        elif candidate.provider == "edge_tts":
            ok, error = generate_edge(candidate, text, target, output_dir)
        else:
            ok, error = False, f"unknown provider {candidate.provider}"

        elapsed = round(time.monotonic() - started, 3)
        if ok:
            generated.append(
                {
                    "number": next_number,
                    "file": f"samples/{next_number}.mp3",
                    "provider": candidate.provider,
                    "voice": candidate.voice,
                    "label": candidate.label,
                    "accent": candidate.accent,
                    "style": candidate.style,
                    "duration_seconds": probe_duration(target),
                    "generation_seconds": elapsed,
                }
            )
            next_number += 1
        else:
            if target.exists():
                target.unlink()
            failures.append(
                {
                    "provider": candidate.provider,
                    "voice": candidate.voice,
                    "label": candidate.label,
                    "reason": error,
                    "elapsed_seconds": elapsed,
                }
            )

    report = {
        "generated_at": generated_at,
        "sample_text": text,
        "seed": SEED,
        "sample_count": len(generated),
        "samples": generated,
        "failures": failures,
        "unavailable": unavailable,
        "not_attempted": [
            {
                "provider": "kokoro_onnx",
                "reason": "Package installed, but the model weights were not generated in this pass because the required model download was too slow on this network.",
            },
            {
                "provider": "piper_tts",
                "reason": "No local Piper executable or British English model bundle was available in the workspace.",
            },
            {
                "provider": "commercial_api_tts",
                "reason": "Skipped paid/API-key providers for this first voice audition because Apple and Edge could generate real samples without adding secrets.",
            },
        ],
    }

    (output_dir / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "index.html").write_text(html_page(generated, text, generated_at), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate numbered TTS samples and a ranking HTML page.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--text", default=DEFAULT_SAMPLE_TEXT)
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args()

    report = generate(args.output_dir.resolve(), args.text, args.max_samples)
    print(f"Generated {report['sample_count']} samples")
    print(args.output_dir.resolve() / "index.html")
    if report["failures"]:
        print(f"{len(report['failures'])} candidates failed; see manifest.json", file=sys.stderr)
    return 0 if report["sample_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
