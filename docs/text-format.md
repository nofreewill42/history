# Text format: reader-md 1

Every file in `texts/` is a Markdown file in the **reader-md 1** format. It is plain Markdown that renders normally anywhere (GitHub, any editor), with a few conventions that let tools find exactly where you are in a text.

## Front matter

Each file starts with YAML front matter:

```yaml
---
id: 1-enoch
title: The Book of Enoch
translator: R. H. Charles        # or `author:` for original works
edition: Translations of Early Documents, Series I (SPCK, London, 1917)
source: Project Gutenberg eBook #77935, https://www.gutenberg.org/ebooks/77935
license: Public domain
format: reader-md 1
---
```

| Field | Meaning |
|---|---|
| `id` | Unique, stable identifier. The file name is always `texts/<id>.md`. Recordings and notes refer to texts by this id. |
| `title` | Human-readable title. Extra fields such as `subtitle` are allowed. |
| `translator` / `author` | Who translated it, or who wrote it. |
| `edition` | Which edition or printing the text comes from. |
| `source` | Where the digital text was taken from (with URL). |
| `license` | Copyright status. |
| `format` | Always `reader-md 1` for this version of the format. |

More fields (for example `tags`) may be added later. Subject views will be generated from them, so files never move.

## Headings: navigation only

Headings (`#`, `##`, `###`, …) give the navigational structure: books, sections, sub-sections. They exist only for navigation. They do not define references, and they may cut across chapters arbitrarily (a section can start or end in the middle of a chapter).

## References: bold, at the start of a passage

Every verse or passage starts with its full reference in bold:

```markdown
**6:2** And the angels, the children of the heaven, saw and lusted after them …
```

- A reference is independent of the headings around it and means the same thing wherever it appears.
- References may appear out of order. Charles, for example, prints chapters 91–93 and some verses in a rearranged order; the file keeps his order, and `**93:1**` is still 93:1.
- A paragraph without a leading reference continues the previous referenced passage.

## Poetry

A line of poetry ends with a backslash, which is a Markdown hard line break:

```markdown
**1:4** And the eternal God will tread upon the earth, (even) on Mount Sinai,\
[And appear from His camp]\
```

## Parallel versions

When the same passage survives in more than one version (for example the Ethiopic and the Greek), each version is a separate blockquote whose first line names it:

```markdown
> *Version E:*
>
> **22:5** …

> *Version G^g:*
>
> **22:5** …
```

## Texts without verses

Papers, articles and other texts without verse numbers follow the same rules with their own reference scheme, such as `**3.2**` for section 3, paragraph 2. A text may also use headings only, with no references.
