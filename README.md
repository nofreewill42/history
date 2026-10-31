# history

Reading ancient texts out loud to figure out what they are trying to say: what story they tell us. Each reading session is recorded while I think aloud, transcribed, and linked back to the exact passages that were on screen. The first text is the Book of Enoch.

## Status

- **Exists:** the first text (`texts/1-enoch.md`), the text format, and the layout for reading sessions.
- **Not built yet:** the reader page that shows a text and records a session. There are no sessions yet.

## Layout

```
texts/      one Markdown file per text, flat (never nested by subject)
sessions/   recordings of reading sessions, with transcripts
docs/       format documentation
CLAUDE.md   rules for AI assistants working in this repo
```

- **[texts/](texts/)**: each text is `texts/<id>.md` in the [reader-md 1 format](docs/text-format.md). Files never move; subject views will be generated later from front-matter fields such as tags. See [adding a text](docs/adding-a-text.md).
  - [1-enoch.md](texts/1-enoch.md): the Book of Enoch, R. H. Charles's 1917 translation (Project Gutenberg #77935, public domain).
- **[sessions/](sessions/README.md)**: one folder per recording, `sessions/<YYYY>/<YYYY-MM-DDTHHMM>/`, holding the audio, what was on screen when (`nav.jsonl`), raw ASR output, and the corrected transcript. A recording belongs to no single text and may span many.
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

5. **Optional: install ffmpeg** (`sudo apt install ffmpeg`, `brew install ffmpeg`, or from [ffmpeg.org](https://ffmpeg.org/download.html)) to encode recordings to Opus as described in [sessions/README.md](sessions/README.md).

## Audio and Git LFS

Session audio (`*.opus`) is stored with Git LFS. GitHub Free includes 10 GiB/month of LFS bandwidth, so when you don't need the audio, clone without downloading it:

```sh
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/nofreewill42/history
```

Original, uncompressed recordings (`sessions/**/original.*`) stay local and are git-ignored.
