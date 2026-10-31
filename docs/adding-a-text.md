# Adding a text

1. **Choose an id.**
   - Lowercase letters, digits and hyphens only, e.g. `1-enoch`, `jubilees`, `4-ezra`.
   - Unique across `texts/`.
   - Never changed later: sessions refer to texts by id, so renaming breaks them.

   The file is `texts/<id>.md`. `texts/` stays flat; never put a text in a subfolder.

2. **Fill in the front matter** as described in [text-format.md](text-format.md#front-matter): `id`, `title`, `translator` or `author`, `edition`, `source` (with URL), `license`, and `format: reader-md 1`. Make sure the text is public domain or that its license allows it to be stored here.

3. **Convert the text to reader-md 1** following [text-format.md](text-format.md):
   - headings for navigation;
   - a bold full reference at the start of every verse or passage (`**6:2**`), kept in the source's own order;
   - a trailing backslash at the end of each poetry line;
   - a separate blockquote for each parallel version, starting with `> *Version X:*`.

4. **Check faithfulness.** Every character of the source text must survive, apart from layout (line breaks, heading markers, blockquote markers, backslashes) and the added reference markers. A good check is a script that strips the reader-md markup from the file and from the source, normalises whitespace, and compares the two character by character. Write down anything deliberately left out (for example an introduction or footnotes) in the text's opening note.

5. **Add it to the README's list of texts**, under `texts/` in [README.md](../README.md), with its title, translator or author, edition and source.

6. **Commit** the text and the README change together, e.g. "Add Book of Jubilees (Charles 1917)".
