"""Real voice-activity detection (Silero VAD), replacing a naive dB-threshold
silence check.

Why this exists: the pipeline originally used ffmpeg's `silencedetect` (a raw
amplitude threshold) to catch a transcript claiming words were spoken during
actual silence. Tested against a real captioned video, it produced a false
positive — several ordinary ~0.3-0.6s speech pauses (breath, the gap between
phrases) summed past a 50% threshold and got called "mostly silent," when a
person was continuously talking throughout. A volume threshold cannot tell
"quiet because nobody's talking" apart from "quiet because of a natural pause
mid-sentence, or a soft-spoken moment." A model trained on what speech actually
looks like can. Silero VAD is that model: small (~2MB, downloads once via
torch.hub, cached after), runs locally, no API key.

Audio is loaded with the stdlib `wave` module + numpy, not torchaudio's own
loader — torchaudio's `sox` backend needs a system `libsox` this environment
doesn't have, and the VAD model itself doesn't need torchaudio's I/O, only its
presence as an import in the upstream repo's utility module.
"""
from __future__ import annotations

import wave

import numpy as np

_model = None
_get_speech_timestamps = None


def available() -> bool:
    try:
        import torch  # noqa: F401
        import torchaudio  # noqa: F401
        return True
    except ImportError:
        return False


def _load_model():
    global _model, _get_speech_timestamps
    if _model is not None:
        return
    import torch
    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad", model="silero_vad",
        force_reload=False, trust_repo=True,
    )
    _model = model
    _get_speech_timestamps = utils[0]


def _read_wav_mono16k(path: str) -> "np.ndarray":
    w = wave.open(path, "rb")
    if w.getframerate() != 16000 or w.getnchannels() != 1:
        raise ValueError(f"{path} must be mono 16kHz (got {w.getnchannels()}ch @ {w.getframerate()}Hz)")
    frames = w.readframes(w.getnframes())
    w.close()
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def detect_speech(audio_16k_wav_path: str) -> list:
    """Returns [(start_sec, end_sec), ...] — intervals where a human voice was
    actually detected. Everything NOT in this list is the real "nothing was
    said here" signal, derived from a speech model instead of a volume knob."""
    import torch
    _load_model()
    audio = _read_wav_mono16k(audio_16k_wav_path)
    wav_tensor = torch.from_numpy(audio)
    timestamps = _get_speech_timestamps(wav_tensor, _model, sampling_rate=16000, return_seconds=True)
    return [(t["start"], t["end"]) for t in timestamps]
