# history

Reading ancient texts out loud to figure out what they are trying to say: what story they tell us. Each reading session is recorded while I think aloud, transcribed, and linked back to the exact passages that were on screen. The first text is the Book of Enoch.

## Layout

```
texts/      one Markdown file per text, flat (never nested by subject)
sessions/   recordings of reading sessions, with transcripts
docs/       format documentation
```

- **[texts/](texts/)**: each text is `texts/<id>.md` in the [reader-md 1 format](docs/text-format.md). Files never move; subject views will be generated later from front-matter fields such as tags.
  - [1-enoch.md](texts/1-enoch.md): the Book of Enoch, R. H. Charles's 1917 translation (Project Gutenberg #77935, public domain).
- **[sessions/](sessions/README.md)**: one folder per recording, `sessions/<YYYY>/<YYYY-MM-DDTHHMM>/`, holding the audio, what was on screen when (`nav.jsonl`), raw ASR output, and the corrected transcript. A recording belongs to no single text and may span many.
- **[docs/](docs/)**: [text format](docs/text-format.md), [session layout](sessions/README.md).

## Audio and Git LFS

Session audio (`*.opus`) is stored with Git LFS. GitHub Free includes 10 GiB/month of LFS bandwidth, so when you don't need the audio, clone without downloading it:

```sh
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/nofreewill42/history
```

Original, uncompressed recordings (`sessions/**/original.*`) stay local and are git-ignored.
