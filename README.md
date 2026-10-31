# history

Reading ancient texts out loud to figure out what they are trying to say: what story they tell us. Each reading session is recorded while I think aloud, transcribed, and linked back to the exact passages that were on screen. The first text is the Book of Enoch.

## Status

- **Exists:** the first text (`texts/1-enoch.md`), the text and session formats, and phase 1 of the [reader and studio](docs/transcription.md): reading any text, recording a session while you move through texts, downloading ASR models, and a transcript after each recording.
- **Not tested yet on a GPU:** the real ASR models. The pipeline has been tested end to end in a browser with a stand-in model; see [what still needs testing](docs/transcription.md#still-to-test-on-the-gpu-machine).
- **Not built yet:** the correction view, other languages, reading vs comment alignment, and training (phases 2 to 5). There are no real sessions yet.

## Layout

```
texts/      one Markdown file per text, flat (never nested by subject)
sessions/   recordings of reading sessions, with transcripts
reader/     the reading page (static HTML/JS)
studio/     local app that serves the page, saves sessions and runs ASR models
tests/      tests for the studio (no model weights needed)
docs/       format and design documentation
CLAUDE.md   rules for AI assistants working in this repo
```

- **[texts/](texts/)**: each text is `texts/<id>.md` in the [reader-md 1 format](docs/text-format.md). Files never move; subject views will be generated later from front-matter fields such as tags. See [adding a text](docs/adding-a-text.md).
  - [1-enoch.md](texts/1-enoch.md): the Book of Enoch, R. H. Charles's 1917 translation (Project Gutenberg #77935, public domain).
- **[sessions/](sessions/README.md)**: one folder per recording, `sessions/<YYYY>/<YYYY-MM-DDTHHMM>/`, holding the audio, what was on screen when (`nav.jsonl`), raw ASR output, and the corrected transcript. A recording belongs to no single text and may span many.
- **[reader/](reader/) and [studio/](studio/)**: the reading page and the local app behind it. See [Run the reader and studio](#run-the-reader-and-studio) and the [design](docs/transcription.md).
- **[docs/](docs/)**: [text format](docs/text-format.md), [adding a text](docs/adding-a-text.md), [session layout](sessions/README.md), [reader, recording and transcription](docs/transcription.md).

## Set up on a new computer

1. **Install git and Git LFS.**

   | System | Command |
   |---|---|
   | Debian / Ubuntu | `sudo apt install git git-lfs` |
   | macOS | `brew install git git-lfs` |
   | Windows | install [Git for Windows](https://gitforwindows.org/), which includes Git LFS |

2. **Turn on Git LFS, once per machine:**

   ```sh
   git lfs install
   ```

   Do this **before committing any audio**. Without it, `.opus` files are committed as normal git files and stay in the history permanently, even if they are deleted later.

3. **Clone:**

   ```sh
   git clone https://github.com/nofreewill42/history
   ```

   To skip downloading the audio, see [Audio and Git LFS](#audio-and-git-lfs) below.

4. **Authenticate for pushing**, with either:
   - the GitHub CLI: `gh auth login`, or
   - SSH: add your SSH key to GitHub and use `git@github.com:nofreewill42/history.git` as the remote.

5. **Install ffmpeg** (`sudo apt install ffmpeg`, `brew install ffmpeg`, or from [ffmpeg.org](https://ffmpeg.org/download.html)). The studio needs it to encode recordings; it is optional if you only read the texts.

## Run the reader and studio

The studio targets Linux with an NVIDIA GPU (developed for an RTX 3090, 24 GB) and also runs on CPU, slowly.

1. **Install uv**, the Python project manager:

   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install the studio** with the ASR engines you want. From the repo folder:

   ```sh
   uv sync --extra whisper                                   # Whisper models only
   uv sync --extra whisper --extra nemo --extra transformers # every engine (large download)
   ```

   uv installs Python 3.12 into `.venv/` if needed. The engines are:

   | Extra | Models |
   |---|---|
   | `whisper` | Whisper large-v3, large-v3 turbo, tiny.en |
   | `nemo` | Parakeet TDT v2 and v3, Canary-Qwen 2.5B |
   | `transformers` | Granite Speech 3.3 8B |

3. **Start it:**

   ```sh
   uv run studio
   ```

   It opens http://localhost:8765/ in your browser. Use `--port` to change the port and `--no-browser` to skip opening it. It listens on this computer only.

4. **First time:** open **Models**, press **Install** on a model, and choose it as **Final** (and **Live** if you want a preview while recording). Weights go to the Hugging Face cache (`~/.cache/huggingface`), not into the repo.

5. **Record:** press **Record**, read and think aloud, move freely between passages and texts, press **Stop**. The session is saved and committed (not pushed), then transcribed with the final model. Push when you're ready:

   ```sh
   git push
   ```

Run the tests with `uv run pytest`.

## Audio and Git LFS

Session audio (`*.opus`) is stored with Git LFS. GitHub Free includes 10 GiB/month of LFS bandwidth, so when you don't need the audio, clone without downloading it:

```sh
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/nofreewill42/history
```

Original, uncompressed recordings (`sessions/**/original.*`) stay local and are git-ignored.
