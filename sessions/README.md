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

The folder name is the local start time of the recording.

### `session.json`

Metadata about the session:

- start time, with timezone offset (e.g. `2026-11-01T21:07:00+01:00`)
- duration
- device / microphone
- free-form notes
- ids of the texts touched, derived from `nav.jsonl`

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
- `ref`: the reference on screen

This is the **only** link between recordings and texts.

### `asr/<model>.json`

Raw speech-recognition output, one file per model: segments, word timestamps, probabilities. Never edited by hand.

### `transcript.jsonl`

The current best transcript, one segment per line:

```json
{"start": 12.34, "end": 17.80, "text": "...", "source": "whisper-v35", "checked": false}
```

Segments get corrected over time, and `checked` is set to `true` once a segment has been verified. Git history keeps every correction. Checked segments together with `audio.opus` are ground-truth training data for a personal speech recognizer.
