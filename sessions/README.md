# Reading sessions

A **session** is one recording of reading out loud and thinking aloud. A session belongs to no particular text: it may cover part of one text, or jump between many. The only link between a recording and the texts is `nav.jsonl`.

## Layout

```
sessions/<YYYY>/<YYYY-MM-DDTHHMM>/        e.g. sessions/2026/2026-11-01T2107/
  session.json
  audio.opus
  original.*          (local only, git-ignored)
  nav.jsonl
  asr/<model>.json
  transcript.jsonl
```

The folder name is the local start time of the recording. If two recordings start in the same minute, the second gets `-2` appended (`2026-11-01T2107-2`), and so on.

Sessions are recorded by the reader page and studio; see [docs/transcription.md](../docs/transcription.md).

### `session.json`

Metadata about the session, exactly in this shape:

```json
{
  "id": "2026-11-01T2107",
  "started": "2026-11-01T21:07:00+01:00",
  "duration_s": 3725.4,
  "device": "...",
  "mic": "...",
  "audio": {"codec": "opus", "bitrate_kbps": 24, "channels": 1},
  "texts": ["1-enoch"],
  "notes": ""
}
```

| Field | Meaning |
|---|---|
| `id` | The session folder name. |
| `started` | Local start time with timezone offset. |
| `duration_s` | Length of the recording in seconds. |
| `device` | The computer or phone used to record. |
| `mic` | The microphone used. |
| `audio` | Encoding of `audio.opus`: codec, bitrate in kbps, number of channels. |
| `texts` | Ids of the texts touched, derived from `nav.jsonl`. |
| `notes` | Free-form notes; empty string if none. |

### `audio.opus`

The whole recording as mono Opus at 24 kbps. Tracked with Git LFS. Reference encode command:

```sh
ffmpeg -i original.wav -ac 1 -c:a libopus -b:a 24k -application voip audio.opus
```

### `original.*`

The untouched original recording (`wav`, `flac`, `webm`, …). It stays on the local machine only and is git-ignored. It is the master copy for future re-encoding or training.

### `nav.jsonl`

One JSON object per line, written by the reader page, recording what was on screen at each moment:

```json
{"t": 12.5, "text": "1-enoch", "ref": "22:5"}
```

- `t`: seconds since the recording started
- `text`: the text's `id` (see [text format](../docs/text-format.md))
- `ref`: the reference on screen, or `null` when no reference is on screen (for example, only a heading)
- `heading` (optional): the text of the heading on screen

When no reference is on screen:

```json
{"t": 3.0, "text": "1-enoch", "ref": null, "heading": "Sheol, or the Underworld (22)"}
```

This is the **only** link between recordings and texts.

### `asr/<model>.json`

Raw speech-recognition output, one file per model, named by the model's `id` from `studio/models.json`. Written by the studio, never edited by hand:

```json
{
  "model": {"id": "whisper-large-v3", "name": "Whisper large-v3", "engine": "faster-whisper",
            "hf_repo": "Systran/faster-whisper-large-v3", "revision": "<Hugging Face commit>"},
  "settings": {"language": "en", "task": "transcribe", "chunk_s": null, "device": "cuda"},
  "created": "2026-11-01T22:15:03+01:00",
  "audio": {"file": "original.wav", "duration_s": 3725.4},
  "segments": [
    {"start": 12.34, "end": 17.8, "text": "...",
     "avg_logprob": -0.21, "no_speech_prob": 0.01,
     "words": [{"start": 12.34, "end": 12.6, "word": "And", "probability": 0.98}]}
  ]
}
```

- `model.revision` is the Hugging Face commit of the weights, or `null` for a local checkpoint.
- `audio.file` is the file that was transcribed: `original.wav` when it exists on that machine, otherwise `audio.opus`.
- `avg_logprob`, `no_speech_prob` and `words` appear only when the model provides them. A word's `probability` may be `null`.

### `transcript.jsonl`

The current best transcript, one segment per line:

```json
{"start": 12.34, "end": 17.8, "text": "...", "source": "whisper-large-v3", "checked": false, "lang": "en", "kind": "comment", "ref": null}
```

| Field | Meaning |
|---|---|
| `start`, `end` | Seconds since the recording started. |
| `text` | The segment's text. |
| `source` | Model `id` the text came from, or `"manual"` for a segment typed by hand. |
| `checked` | `true` once the segment has been verified by ear. |
| `lang` | ISO language code. `"en"` until language identification exists (phase 3). |
| `kind` | `"reading"` (reading the text aloud) or `"comment"` (thinking aloud). Everything is `"comment"` until alignment exists (phase 4). |
| `ref` | For `"reading"` segments, the reference being read; otherwise `null`. |

The first final transcription pass seeds this file. A later re-run replaces it only while no segment is `checked`. See [docs/transcription.md](../docs/transcription.md).

Segments get corrected over time, and `checked` is set to `true` once a segment has been verified. Git history keeps every correction. Checked segments together with `audio.opus` are ground-truth training data for a personal speech recognizer.
