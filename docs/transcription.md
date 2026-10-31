# Reader, recording and transcription

How reading sessions are recorded and transcribed. File formats are defined in [sessions/README.md](../sessions/README.md) and [text-format.md](text-format.md); this document describes the tools and the plan.

| Phase | What | Status |
|---|---|---|
| 1 | Reader page, studio, recording, models panel, final pass, live preview | **built** |
| 2 | Correction view | planned |
| 3 | Language ID per segment, prompt biasing | planned |
| 4 | Reading vs comment alignment | planned |
| 5 | Training and evaluation | planned |

## Architecture

```
browser ── reader/ (static HTML/JS) ──HTTP──▶ studio/ (FastAPI, local) ──▶ texts/, sessions/, git, ffmpeg, GPU
```

- **`reader/`**: a static page (HTML/JS, no build step). It shows any text from `texts/`, parsing [reader-md 1](text-format.md), with sidebar navigation built from the headings. A recording bar stays at the bottom of the page and keeps recording while you move between sections and texts, because the page never reloads.
- **`studio/`**: a local Python app (FastAPI, managed with uv, started with `uv run studio`). It serves `reader/` and `texts/`, saves sessions into `sessions/`, runs ffmpeg, and downloads and runs ASR models on the local GPU (target: Linux, RTX 3090 24 GB, CUDA). The page talks only to the studio.

Setup is in the [README](../README.md#run-the-reader-and-studio).

## Recording

1. **Record** in the page starts a session. The studio creates `sessions/<YYYY>/<YYYY-MM-DDTHHMM>/`.
2. The page captures raw 16-bit PCM from the microphone (an AudioWorklet, no browser compression) and sends it to the studio every 5 seconds. The studio appends each chunk to `original.wav` on disk straight away, so a crash loses at most the last few seconds.
3. While recording, the page logs every change of position (scrolling, sidebar jumps, switching texts) to `nav.jsonl`. `t` is measured on the audio clock (samples recorded so far), so it lines up exactly with the audio.
4. **Stop** finalises the session:
   - fixes the WAV header of `original.wav` (git-ignored, local only);
   - encodes `audio.opus` (24 kbps mono, Git LFS) with ffmpeg;
   - writes `session.json`;
   - commits the session folder to git. It never pushes.
5. If the studio or browser dies mid-recording, the next `uv run studio` finds the unfinished session (`original.wav` without `session.json`) and finalises it the same way, with `"notes": "recovered after interruption"`.

The studio commits only if Git LFS is installed and `audio.opus` resolves to the `lfs` filter. Otherwise it leaves the session uncommitted and shows a warning.

## Models

### Registry

- **`studio/models.json`** (in the repo) is the curated registry. Each entry has:

  | Field | Meaning |
  |---|---|
  | `id` | Short stable id, used in file names: `asr/<id>.json` and `"source": "<id>"` |
  | `name` | Display name |
  | `engine` | `nemo`, `faster-whisper` or `transformers` |
  | `hf_repo` | Hugging Face repo the weights are downloaded from |
  | `converted_from` | (optional) original repo, when `hf_repo` is a conversion |
  | `languages` | ISO codes |
  | `english_only` | `true` if the model only does English |
  | `params` | Parameter count, as a string such as `"0.6B"` |
  | `vram_gb` | Rough GPU memory needed for inference (estimate) |
  | `license` | Weights license |
  | `word_timestamps` | Whether the model gives word-level timestamps |
  | `supports_prompt` | Whether it accepts text context for prompt biasing (phase 3) |
  | `chunk_s` | (optional) longest audio the studio feeds it at once; longer audio is split |
  | `nemo_class` | (optional, nemo only) `"SALM"` for speech-LLMs like Canary-Qwen; default is NeMo's `ASRModel` |
  | `notes` | Anything else worth knowing |

- **`studio/local.json`** (git-ignored) lists your own fine-tuned checkpoints, by local path in `hf_repo`, with the same fields. It is merged into the list.

Initial entries:

| id | Repo | Engine | Notes |
|---|---|---|---|
| `canary-qwen-2.5b` | nvidia/canary-qwen-2.5b | nemo | English only, no timestamps, needs NeMo from git trunk |
| `parakeet-tdt-0.6b-v2` | nvidia/parakeet-tdt-0.6b-v2 | nemo | English only, word timestamps |
| `parakeet-tdt-0.6b-v3` | nvidia/parakeet-tdt-0.6b-v3 | nemo | 25 European languages incl. Hungarian, word timestamps |
| `whisper-large-v3` | Systran/faster-whisper-large-v3 (from openai/whisper-large-v3) | faster-whisper | 99 languages, word timestamps and probabilities |
| `whisper-large-v3-turbo` | dropbox-dash/faster-whisper-large-v3-turbo (from openai/whisper-large-v3-turbo) | faster-whisper | Much faster than large-v3, slightly less accurate |
| `granite-speech-3.3-8b` | ibm-granite/granite-speech-3.3-8b | transformers | en, fr, de, es, pt; no timestamps; ~17 GB in bf16 |
| `whisper-tiny.en` | Systran/faster-whisper-tiny.en | faster-whisper | Pipeline tests only |

The Whisper models use faster-whisper (CTranslate2), which loads converted copies of OpenAI's weights. These are the repos faster-whisper itself uses, and they give word probabilities, which the transformers pipeline does not.

### Models panel

The page's **Models** panel lists every model with its status: whether the engine package is installed, whether the weights are downloaded, and a running download if any. From there you can:

- **Install**: download the weights into the Hugging Face cache (`~/.cache/huggingface`), outside the repo.
- **Delete**: remove the weights from the cache.
- Choose the **default live model** and the **default final model**. These choices are stored in `studio/settings.json` (git-ignored).

Engine packages are Python extras, installed with uv: `uv sync --extra whisper`, `--extra nemo`, `--extra transformers`. The panel says which one is missing.

## Transcription

### Live pass (optional)

A toggle in the recording bar. While recording, the studio runs the default live model over the last ~15 seconds every few seconds and the page shows the result as preview text in the recording bar. Nothing is saved.

### Final pass

After **Stop**, the studio runs the default final model over the whole recording:

- Audio is converted to 16 kHz mono first. Models with a `chunk_s` limit get the audio in chunks, each cut at the quietest point in its last few seconds to avoid cutting words, with timestamps shifted back to the whole recording.
- The output goes to `sessions/.../asr/<model-id>.json`: segments, word timestamps, probabilities, model id and version (the Hugging Face commit), settings and date.
- If the session has no `transcript.jsonl` yet, it is seeded from this output.
- The ASR output and the seeded transcript are committed to git.

Any model can be run again later on any session from the page. A re-run writes its own `asr/<model-id>.json` and replaces `transcript.jsonl` only if no segment in it has been checked yet.

### English first

Every model runs with the language fixed to English. For Whisper that is `language="en", task="transcribe"`; the studio never asks a model to translate.

### Phase 3: other languages and prompt biasing

- **Language ID per segment.** Non-English segments get `"lang": "hu"` (etc.) and are re-transcribed with a multilingual model in that language. The page shows a live indicator while a non-English stretch is detected, and `session.json` gains `"non_english_s"` (seconds of non-English speech).
- **Prompt biasing.** Models with `supports_prompt` get the rare words and names from the passages on screen (from `nav.jsonl`) as context.

### Phase 4: reading vs comment

Segments are aligned to the passage on screen. Segments that match the passage get `"kind": "reading"` and its `"ref"`; the rest are `"kind": "comment"`. Reading segments become training data with the book text as the label. Diacritics, brackets and markup are normalised away when comparing.

### `transcript.jsonl`

```json
{"start": 12.34, "end": 17.8, "text": "...", "source": "<model-id>", "checked": false, "lang": "en", "kind": "comment", "ref": null}
```

Until phase 4 exists, every segment is seeded with `"kind": "comment"` and `"ref": null`. The full field list is in [sessions/README.md](../sessions/README.md#transcriptjsonl).

## Phase 2: correction view

The transcript next to the audio. Click a segment to play it, edit with the keyboard, mark segments checked. Saves `transcript.jsonl`.

## Phase 5: training

Export checked segments and reading segments as a dataset. Fine-tune Whisper or Parakeet, register the result in `studio/local.json`, and evaluate every model by word error rate on a held-out set of checked segments.
