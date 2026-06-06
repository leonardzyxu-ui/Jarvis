"""Persistent Piper worker for lower-latency speech playback."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any

from piper import PiperVoice, SynthesisConfig
from piper.phonemize_espeak import ESPEAK_DATA_DIR


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a warm Piper speech worker over JSON lines.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--espeak-data")
    parser.add_argument("--afplay", required=True)
    return parser.parse_args()


def _emit(event: str, **data: Any) -> None:
    payload = {"event": event, **data}
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def _chunk_text(text: str) -> list[str]:
    clean = re.sub(r"\s+", " ", text.strip())
    if not clean:
        return []
    first_target = 45
    later_target = 180
    pieces = re.split(r"(?<=[.!?;:])\s+", clean)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(piece) > 180:
            subpieces = re.split(r"(?<=,)\s+", piece)
        else:
            subpieces = [piece]
        for subpiece in subpieces:
            subpiece = subpiece.strip()
            if not subpiece:
                continue
            target = first_target if not chunks else later_target
            if current and len(current) + 1 + len(subpiece) <= target:
                current = f"{current} {subpiece}"
                continue
            if current:
                chunks.append(current)
            current = subpiece
    if current:
        chunks.append(current)
    if len(chunks) <= 1 and len(clean) > 140:
        chunks = [clean[index : index + 140].strip() for index in range(0, len(clean), 140)]
    if chunks and len(chunks[0]) > 34:
        words = chunks[0].split()
        first_words: list[str] = []
        remaining_words: list[str] = []
        for word in words:
            candidate = " ".join([*first_words, word])
            if first_words and len(candidate) > 32:
                remaining_words.append(word)
            elif remaining_words:
                remaining_words.append(word)
            else:
                first_words.append(word)
        first = " ".join(first_words).strip()
        rest = " ".join(remaining_words).strip()
        if len(first) >= 12 and rest:
            chunks = [first, rest, *chunks[1:]]
    return [chunk for chunk in chunks if chunk]


class SpeechState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.current_id: str | None = None
        self.current_generation = 0
        self.current_stop: threading.Event | None = None
        self.current_player: subprocess.Popen[str] | None = None

    def start_job(self, speech_id: str) -> tuple[int, threading.Event]:
        with self.lock:
            self.stop_current_locked()
            self.current_generation += 1
            stop_event = threading.Event()
            self.current_id = speech_id
            self.current_stop = stop_event
            self.current_player = None
            return self.current_generation, stop_event

    def stop_current_locked(self) -> bool:
        stopped = False
        if self.current_stop is not None:
            self.current_stop.set()
            stopped = True
        if self.current_player is not None and self.current_player.poll() is None:
            try:
                self.current_player.terminate()
            except OSError:
                pass
            stopped = True
        return stopped

    def stop_current(self) -> bool:
        with self.lock:
            return self.stop_current_locked()

    def is_current(self, speech_id: str, generation: int) -> bool:
        with self.lock:
            return self.current_id == speech_id and self.current_generation == generation

    def set_player(self, speech_id: str, generation: int, player: subprocess.Popen[str] | None) -> None:
        with self.lock:
            if self.current_id == speech_id and self.current_generation == generation:
                self.current_player = player

    def finish(self, speech_id: str, generation: int) -> None:
        with self.lock:
            if self.current_id == speech_id and self.current_generation == generation:
                self.current_id = None
                self.current_stop = None
                self.current_player = None


def _synthesize_to_wav(voice: PiperVoice, syn_config: SynthesisConfig, text: str, wav_path: Path) -> None:
    params_set = False
    with wave.open(str(wav_path), "wb") as wav_file:
        for audio_chunk in voice.synthesize(text, syn_config):
            if not params_set:
                wav_file.setframerate(audio_chunk.sample_rate)
                wav_file.setsampwidth(audio_chunk.sample_width)
                wav_file.setnchannels(audio_chunk.sample_channels)
                params_set = True
            wav_file.writeframes(audio_chunk.audio_int16_bytes)


def _play_job(
    *,
    state: SpeechState,
    voice: PiperVoice,
    voice_lock: threading.Lock,
    syn_config: SynthesisConfig,
    afplay: str,
    speech_id: str,
    text: str,
    generation: int,
    stop_event: threading.Event,
) -> None:
    started_at = time.monotonic()
    chunks = _chunk_text(text)
    first_audio_at: float | None = None
    played_chunks = 0
    try:
        for index, chunk in enumerate(chunks):
            if stop_event.is_set() or not state.is_current(speech_id, generation):
                _emit("stopped", id=speech_id, chunks_played=played_chunks)
                return
            with tempfile.TemporaryDirectory(prefix="jarvis-piper-warm-") as tmpdir:
                wav_path = Path(tmpdir) / f"chunk-{index}.wav"
                synth_started = time.monotonic()
                with voice_lock:
                    _synthesize_to_wav(voice, syn_config, chunk, wav_path)
                synth_seconds = round(time.monotonic() - synth_started, 3)
                if stop_event.is_set() or not state.is_current(speech_id, generation):
                    _emit("stopped", id=speech_id, chunks_played=played_chunks)
                    return
                player = subprocess.Popen(
                    [afplay, str(wav_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                state.set_player(speech_id, generation, player)
                if first_audio_at is None:
                    first_audio_at = time.monotonic()
                    _emit(
                        "first_audio",
                        id=speech_id,
                        first_audio_seconds=round(first_audio_at - started_at, 3),
                        first_chunk_chars=len(chunk),
                        first_chunk_synth_seconds=synth_seconds,
                    )
                while player.poll() is None:
                    if stop_event.is_set() or not state.is_current(speech_id, generation):
                        try:
                            player.terminate()
                        except OSError:
                            pass
                        _emit("stopped", id=speech_id, chunks_played=played_chunks)
                        return
                    time.sleep(0.02)
                if player.returncode != 0:
                    _emit("error", id=speech_id, status="playback_failed", returncode=player.returncode)
                    return
                played_chunks += 1
                state.set_player(speech_id, generation, None)
        _emit(
            "done",
            id=speech_id,
            chunks_played=played_chunks,
            first_audio_seconds=round(first_audio_at - started_at, 3) if first_audio_at else None,
            duration_seconds=round(time.monotonic() - started_at, 3),
        )
    except Exception as error:  # noqa: BLE001 - report errors to parent instead of crashing silently.
        _emit("error", id=speech_id, status="worker_exception", error=str(error)[-500:])
    finally:
        state.finish(speech_id, generation)


def main() -> int:
    args = _parse_args()
    model_path = Path(args.model).expanduser()
    config_path = Path(args.config).expanduser()
    espeak_data_dir = Path(args.espeak_data).expanduser() if args.espeak_data else ESPEAK_DATA_DIR
    load_started = time.monotonic()
    try:
        voice = PiperVoice.load(model_path, config_path=config_path, espeak_data_dir=espeak_data_dir)
    except Exception as error:  # noqa: BLE001
        _emit("fatal", status="load_failed", error=str(error)[-500:])
        return 2
    syn_config = SynthesisConfig()
    prime_started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="jarvis-piper-prime-") as tmpdir:
            _synthesize_to_wav(voice, syn_config, "Ready.", Path(tmpdir) / "prime.wav")
        prime_seconds = round(time.monotonic() - prime_started, 3)
    except Exception:  # noqa: BLE001 - priming is an optimization, not required for speech.
        prime_seconds = None
    state = SpeechState()
    voice_lock = threading.Lock()
    _emit(
        "ready",
        load_seconds=round(time.monotonic() - load_started, 3),
        prime_seconds=prime_seconds,
        model=str(model_path),
        config=str(config_path),
        espeak_data=str(espeak_data_dir),
    )
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            message = json.loads(raw_line)
        except json.JSONDecodeError:
            _emit("error", status="bad_json")
            continue
        message_type = str(message.get("type") or "")
        if message_type == "stop":
            stopped = state.stop_current()
            _emit("stop_ack", id=message.get("id"), stopped=stopped)
            continue
        if message_type == "shutdown":
            state.stop_current()
            _emit("shutdown")
            return 0
        if message_type != "speak":
            _emit("error", status="unknown_message", type=message_type)
            continue
        speech_id = str(message.get("id") or "")
        text = str(message.get("text") or "").strip()
        if not speech_id or not text:
            _emit("error", id=speech_id, status="missing_speech_payload")
            continue
        generation, stop_event = state.start_job(speech_id)
        _emit("accepted", id=speech_id, chunks=len(_chunk_text(text)), text_length=len(text))
        thread = threading.Thread(
            target=_play_job,
            kwargs={
                "state": state,
                "voice": voice,
                "voice_lock": voice_lock,
                "syn_config": syn_config,
                "afplay": args.afplay,
                "speech_id": speech_id,
                "text": text,
                "generation": generation,
                "stop_event": stop_event,
            },
            daemon=True,
        )
        thread.start()
    state.stop_current()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
