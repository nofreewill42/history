# Notes for AI assistants

## Purpose

This repo is for reading ancient texts out loud and figuring out what story they tell. Texts live in `texts/`. Reading sessions (audio of reading and thinking aloud, what was on screen when, and transcripts) live in `sessions/`. See [README.md](README.md) for the overview.

## Rules

- **Never edit the content of files in `texts/`.** Each text has been checked against its source. Fix a text only when the owner asks for that fix, and cite the source that justifies it (edition, page or URL) in the commit message.
- **Follow the formats exactly.**
  - Texts: [docs/text-format.md](docs/text-format.md) (reader-md 1). To add a text, follow [docs/adding-a-text.md](docs/adding-a-text.md).
  - Sessions: [sessions/README.md](sessions/README.md): folder names, file names and JSON field names.
  - Reader, studio, recording and transcription design: [docs/transcription.md](docs/transcription.md). Check its phase table before building anything new.
- **Clone without audio unless you need it:**

  ```sh
  GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/nofreewill42/history
  ```

- **Audio goes through Git LFS.** Run `git lfs install` before committing any `.opus` file, and check that `git check-attr filter -- <file>` reports `lfs`. If an LFS push fails, stop and report it; never commit audio without LFS.
- **Never commit `original.*` files.** They are local-only master recordings and are git-ignored.
- **Run the tests** with `uv run pytest` after changing `studio/`. They need no model weights.
- **The studio commits sessions itself** (never pushes). When testing it, run it in a throwaway clone so test sessions don't end up in this repo's history.
- **Keep commits small and descriptive:** one logical change per commit, with a message saying what changed and why.
