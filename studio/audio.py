"""WAV writing, ffmpeg encoding, and audio loading for ASR."""

from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np

ASR_RATE = 16000


# --- crash-safe WAV writer -------------------------------------------------
# The header is rewritten after every chunk, so original.wav is a valid file
# at all times and a crash loses only audio that never reached the studio.

def _header(sample_rate: int, data_bytes: int, channels: int = 1, bits: int = 16) -> bytes:
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return (
        b"RIFF" + struct.pack("<I", 36 + data_bytes) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits)
        + b"data" + struct.pack("<I", data_bytes)
    )


def wav_create(path: Path, sample_rate: int) -> None:
    path.write_bytes(_header(sample_rate, 0))


def wav_append(path: Path, pcm16: bytes) -> int:
    """Append mono 16-bit PCM and fix the header. Returns total data bytes."""
    if len(pcm16) % 2:
        raise ValueError("PCM chunk must have an even number of bytes")
    with open(path, "r+b") as f:
        f.seek(0, 2)
        f.write(pcm16)
        data_bytes = f.tell() - 44
        f.seek(4)
        f.write(struct.pack("<I", 36 + data_bytes))
        f.seek(40)
        f.write(struct.pack("<I", data_bytes))
    return data_bytes


def wav_info(path: Path) -> tuple[int, int]:
    """(sample_rate, data_bytes) of a mono 16-bit WAV written by wav_create.

    The data size is taken from the file length, so a header that was not
    updated before a crash does not matter.
    """
    with open(path, "rb") as f:
        head = f.read(44)
    sample_rate = struct.unpack("<I", head[24:28])[0]
    data_bytes = max(0, path.stat().st_size - 44)
    data_bytes -= data_bytes % 2
    return sample_rate, data_bytes


def wav_repair(path: Path) -> float:
    """Make the header match the file length. Returns duration in seconds."""
    sample_rate, data_bytes = wav_info(path)
    with open(path, "r+b") as f:
        f.truncate(44 + data_bytes)
        f.seek(4)
        f.write(struct.pack("<I", 36 + data_bytes))
        f.seek(40)
        f.write(struct.pack("<I", data_bytes))
    return data_bytes / 2 / sample_rate


def wav_tail(path: Path, seconds: float) -> np.ndarray:
    """Last `seconds` of the WAV as float32 at 16 kHz (for the live preview)."""
    sample_rate, data_bytes = wav_info(path)
    n = min(data_bytes // 2, int(seconds * sample_rate))
    with open(path, "rb") as f:
        f.seek(44 + data_bytes - 2 * n)
        raw = f.read(2 * n)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return resample(x, sample_rate, ASR_RATE)


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Linear resampling; good enough for the live preview, not for the final pass."""
    if src == dst or len(x) == 0:
        return x.astype(np.float32)
    n = int(round(len(x) * dst / src))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


# --- ffmpeg ----------------------------------------------------------------

def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def encode_opus(src: Path, dst: Path) -> None:
    """The reference encode from sessions/README.md: mono Opus, 24 kbps, voip."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
         "-ac", "1", "-c:a", "libopus", "-b:a", "24k", "-application", "voip", str(dst)],
        check=True,
    )


def load_for_asr(src: Path) -> np.ndarray:
    """Decode any audio file to float32 mono 16 kHz with ffmpeg."""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(src),
         "-ac", "1", "-ar", str(ASR_RATE), "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(out, dtype="<f4").copy()


def write_wav16k(x: np.ndarray, dst: Path) -> None:
    """Write float32 16 kHz mono audio as 16-bit WAV (for engines that want files)."""
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    dst.write_bytes(_header(ASR_RATE, len(pcm)) + pcm)


# --- chunking for models with a length limit --------------------------------

def split_points(x: np.ndarray, chunk_s: float, search_s: float = 5.0, rate: int = ASR_RATE) -> list[tuple[int, int]]:
    """Split audio into pieces of at most chunk_s seconds.

    Each cut is placed at the quietest 50 ms window within the last search_s
    seconds of the piece, so cuts tend to fall between words.
    """
    total = len(x)
    max_len = int(chunk_s * rate)
    if total <= max_len:
        return [(0, total)]
    win = int(0.05 * rate)
    search = min(int(search_s * rate), max_len // 2)
    pieces, start = [], 0
    while total - start > max_len:
        lo, hi = start + max_len - search, start + max_len
        seg = x[lo:hi]
        n = len(seg) // win
        energy = (seg[: n * win].reshape(n, win) ** 2).mean(axis=1)
        cut = lo + int(np.argmin(energy)) * win + win // 2
        pieces.append((start, cut))
        start = cut
    pieces.append((start, total))
    return pieces
