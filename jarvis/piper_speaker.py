"""Small process wrapper for Piper speech playback."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


_SYNTHESIZE_CODE = r"""
import sys
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig
from piper.phonemize_espeak import ESPEAK_DATA_DIR

model_path = Path(sys.argv[1])
config_path = Path(sys.argv[2])
wav_path = Path(sys.argv[3])
espeak_data_dir = Path(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else ESPEAK_DATA_DIR
length_scale = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else 0.76
text = sys.stdin.read().strip()
if not text:
    raise SystemExit(2)

voice = PiperVoice.load(
    model_path,
    config_path=config_path,
    espeak_data_dir=espeak_data_dir,
)
syn_config = SynthesisConfig(length_scale=length_scale)
params_set = False
with wave.open(str(wav_path), "wb") as wav_file:
    for audio_chunk in voice.synthesize(text, syn_config):
        if not params_set:
            wav_file.setframerate(audio_chunk.sample_rate)
            wav_file.setsampwidth(audio_chunk.sample_width)
            wav_file.setnchannels(audio_chunk.sample_channels)
            params_set = True
        wav_file.writeframes(audio_chunk.audio_int16_bytes)
"""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synthesize stdin with Piper and play the resulting WAV.")
    parser.add_argument("--piper-bin", required=True)
    parser.add_argument("--piper-python")
    parser.add_argument("--model", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--espeak-data")
    parser.add_argument("--afplay", required=True)
    parser.add_argument("--piper-timeout", type=float, default=8.0)
    parser.add_argument("--length-scale", type=float, default=0.76)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    text = sys.stdin.read().strip()
    if not text:
        print("No text received.", file=sys.stderr)
        return 2

    model_path = Path(args.model).expanduser()
    config_path = Path(args.config).expanduser()
    if not model_path.exists():
        print(f"Missing Piper model: {model_path}", file=sys.stderr)
        return 3
    if not config_path.exists():
        print(f"Missing Piper config: {config_path}", file=sys.stderr)
        return 4

    with tempfile.TemporaryDirectory(prefix="jarvis-piper-") as tmpdir:
        wav_path = Path(tmpdir) / "speech.wav"
        piper_python = args.piper_python
        if not piper_python:
            sibling_python = Path(args.piper_bin).expanduser().parent / "python"
            if sibling_python.exists():
                piper_python = str(sibling_python)
        env = os.environ.copy()
        env.setdefault("PYTHONNOUSERSITE", "1")
        if piper_python:
            synth_command = [
                piper_python,
                "-c",
                _SYNTHESIZE_CODE,
                str(model_path),
                str(config_path),
                str(wav_path),
                str(Path(args.espeak_data).expanduser()) if args.espeak_data else "",
                str(args.length_scale),
            ]
        else:
            synth_command = [
                args.piper_bin,
                "-m",
                str(model_path),
                "-c",
                str(config_path),
                "-f",
                str(wav_path),
                "--length-scale",
                str(args.length_scale),
            ]
        synth = subprocess.run(
            synth_command,
            input=text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.piper_timeout,
            check=False,
            env=env,
        )
        if synth.returncode != 0:
            print((synth.stderr or synth.stdout or "Piper failed.").strip(), file=sys.stderr)
            return synth.returncode or 5
        played = subprocess.run(
            [args.afplay, str(wav_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if played.returncode != 0:
            print((played.stderr or played.stdout or "Audio playback failed.").strip(), file=sys.stderr)
        return played.returncode


if __name__ == "__main__":
    raise SystemExit(main())
