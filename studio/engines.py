"""ASR engines. Each turns 16 kHz mono float32 audio into segments.

Segment format (times in seconds from the start of the audio passed in):
    {"start", "end", "text", ["avg_logprob", "no_speech_prob", "words": [...]]}
Word format: {"start", "end", "word", "probability" (may be None)}
"""

from __future__ import annotations

import ctypes
import gc
import importlib.util
import tempfile
import threading
from pathlib import Path

import numpy as np

from . import audio, models

LANGUAGE = "en"  # English first: every model runs with English fixed


def _round(x):
    return None if x is None else round(float(x), 3)


def _cuda_available() -> bool:
    if importlib.util.find_spec("torch") is not None:
        import torch
        return torch.cuda.is_available()
    if importlib.util.find_spec("ctranslate2") is not None:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    return False


def _preload_cuda_libs() -> None:
    """Load cuBLAS/cuDNN from the nvidia-* pip wheels so CTranslate2 finds them
    without LD_LIBRARY_PATH. Harmless when they are not installed."""
    libs = []
    for pkg in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            continue
        if spec and spec.submodule_search_locations:
            libs += sorted((Path(spec.submodule_search_locations[0]) / "lib").glob("lib*.so*"))
    pending = libs
    while pending:  # retry until no progress: some libs depend on others
        failed = []
        for lib in pending:
            try:
                ctypes.CDLL(str(lib), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                failed.append(lib)
        if len(failed) == len(pending):
            break
        pending = failed


class Engine:
    def __init__(self, entry: dict, path: Path):
        self.entry, self.path = entry, path
        self.device = "cuda" if _cuda_available() else "cpu"

    def settings(self) -> dict:
        return {"language": LANGUAGE, "task": "transcribe", "chunk_s": self.entry.get("chunk_s"), "device": self.device}

    def transcribe(self, x: np.ndarray, prompt: str | None = None, progress=None) -> list[dict]:
        raise NotImplementedError

    def unload(self) -> None:
        pass


class FasterWhisper(Engine):
    BEAM = 5

    def __init__(self, entry, path):
        _preload_cuda_libs()
        super().__init__(entry, path)
        from faster_whisper import WhisperModel
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        self.model = WhisperModel(str(path), device=self.device, compute_type=self.compute_type)

    def settings(self):
        return dict(super().settings(), compute_type=self.compute_type, beam_size=self.BEAM,
                    vad_filter=True, condition_on_previous_text=False, word_timestamps=True)

    def transcribe(self, x, prompt=None, progress=None):
        segs, _info = self.model.transcribe(
            x, language=LANGUAGE, task="transcribe", beam_size=self.BEAM,
            word_timestamps=True, vad_filter=True, condition_on_previous_text=False,
            initial_prompt=prompt,
        )
        out, duration = [], max(len(x) / audio.ASR_RATE, 1e-6)
        for s in segs:
            if progress:
                progress(min(1.0, s.end / duration))
            out.append({
                "start": _round(s.start), "end": _round(s.end), "text": s.text.strip(),
                "avg_logprob": _round(s.avg_logprob), "no_speech_prob": _round(s.no_speech_prob),
                "words": [{"start": _round(w.start), "end": _round(w.end), "word": w.word.strip(),
                           "probability": _round(w.probability)} for w in (s.words or [])],
            })
        return out

    def unload(self):
        del self.model


class Nemo(Engine):
    def __init__(self, entry, path):
        super().__init__(entry, path)
        self.salm = entry.get("nemo_class") == "SALM"
        if self.salm:
            from nemo.collections.speechlm2.models import SALM
            try:
                self.model = SALM.from_pretrained(str(path))
            except Exception:
                self.model = SALM.from_pretrained(entry["hf_repo"])
        else:
            import nemo.collections.asr as nemo_asr
            nemo_files = sorted(Path(path).glob("*.nemo")) if Path(path).is_dir() else [Path(path)]
            if nemo_files:
                self.model = nemo_asr.models.ASRModel.restore_from(str(nemo_files[0]))
            else:
                self.model = nemo_asr.models.ASRModel.from_pretrained(entry["hf_repo"])
        self.model = self.model.to(self.device).eval()

    def transcribe(self, x, prompt=None, progress=None):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "chunk.wav"
            audio.write_wav16k(x, wav)
            if self.salm:
                return self._salm(wav, len(x))
            return self._asr(wav, len(x))

    def _salm(self, wav, n):
        ids = self.model.generate(
            prompts=[[{"role": "user", "content": f"Transcribe the following: {self.model.audio_locator_tag}",
                       "audio": [str(wav)]}]],
            max_new_tokens=256,
        )
        text = self.model.tokenizer.ids_to_text(ids[0].cpu()).strip()
        return [{"start": 0.0, "end": _round(n / audio.ASR_RATE), "text": text}] if text else []

    def _asr(self, wav, n):
        out = self.model.transcribe([str(wav)], timestamps=True)
        if isinstance(out, tuple):  # some NeMo versions return (hypotheses, all_hypotheses)
            out = out[0]
        hyp = out[0]
        ts = getattr(hyp, "timestamp", None) or {}
        words = [{"start": _round(w.get("start")), "end": _round(w.get("end")),
                  "word": w.get("word", ""), "probability": None} for w in ts.get("word", [])]
        segs = ts.get("segment") or []
        if not segs:
            text = getattr(hyp, "text", str(hyp)).strip()
            return [{"start": 0.0, "end": _round(n / audio.ASR_RATE), "text": text, "words": words}] if text else []
        out_segs = []
        for s in segs:
            start, end = _round(s.get("start")), _round(s.get("end"))
            out_segs.append({"start": start, "end": end, "text": s.get("segment", "").strip(),
                             "words": [w for w in words if w["start"] is not None and start <= w["start"] < end + 1e-3]})
        return out_segs

    def unload(self):
        del self.model


class Transformers(Engine):
    """Speech-LLMs driven through a chat template (Granite Speech)."""

    SYSTEM = "You are Granite, developed by IBM. You are a helpful AI assistant"
    USER = "<|audio|>can you transcribe the speech into a written format?"

    def __init__(self, entry, path):
        super().__init__(entry, path)
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(str(path))
        self.tokenizer = self.processor.tokenizer
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            str(path), device_map=self.device,
            torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
        )

    def transcribe(self, x, prompt=None, progress=None):
        chat = [{"role": "system", "content": self.SYSTEM}, {"role": "user", "content": self.USER}]
        text_prompt = self.tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
        wav = self.torch.from_numpy(x).unsqueeze(0)
        inputs = self.processor(text_prompt, wav, device=self.device, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            outputs = self.model.generate(**inputs, max_new_tokens=256, do_sample=False, num_beams=1)
        new = outputs[0, inputs["input_ids"].shape[-1]:].unsqueeze(0)
        text = self.tokenizer.batch_decode(new, add_special_tokens=False, skip_special_tokens=True)[0].strip()
        return [{"start": 0.0, "end": _round(len(x) / audio.ASR_RATE), "text": text}] if text else []

    def unload(self):
        del self.model


ENGINES = {"faster-whisper": FasterWhisper, "nemo": Nemo, "transformers": Transformers}


# --- loaded-model cache --------------------------------------------------------

_loaded: dict[str, Engine] = {}
_load_lock = threading.Lock()
MAX_LOADED = 2  # the live model and the final model


def load(model_id: str) -> Engine:
    with _load_lock:
        if model_id in _loaded:
            return _loaded[model_id]
        entry = models.get(model_id)
        missing = models.engine_missing(entry["engine"])
        if missing:
            extra = models.ENGINE_EXTRA[entry["engine"]]
            raise RuntimeError(f"engine '{entry['engine']}' is not installed (missing {', '.join(missing)}); "
                               f"run: uv sync --extra {extra}")
        path = models.local_path(entry)
        if path is None:
            raise RuntimeError(f"model '{model_id}' is not downloaded; install it in the Models panel")
        while len(_loaded) >= MAX_LOADED:
            _unload(next(iter(_loaded)))
        _loaded[model_id] = ENGINES[entry["engine"]](entry, path)
        return _loaded[model_id]


def _unload(model_id: str) -> None:
    eng = _loaded.pop(model_id, None)
    if eng is not None:
        eng.unload()
    gc.collect()
    if importlib.util.find_spec("torch") is not None:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def unload(model_id: str) -> None:
    with _load_lock:
        _unload(model_id)


def run(engine: Engine, x: np.ndarray, prompt: str | None = None, progress=None) -> list[dict]:
    """Transcribe audio of any length, splitting it for models with chunk_s."""
    chunk_s = engine.entry.get("chunk_s")
    pieces = audio.split_points(x, chunk_s) if chunk_s else [(0, len(x))]
    segments = []
    for i, (a, b) in enumerate(pieces):
        offset = a / audio.ASR_RATE
        inner = (lambda f, i=i: progress((i + f) / len(pieces))) if progress else None
        for s in engine.transcribe(x[a:b], prompt, inner):
            s["start"], s["end"] = _round(s["start"] + offset), _round(s["end"] + offset)
            for w in s.get("words", []):
                if w["start"] is not None:
                    w["start"], w["end"] = _round(w["start"] + offset), _round(w["end"] + offset)
            segments.append(s)
        if progress:
            progress((i + 1) / len(pieces))
    return segments
