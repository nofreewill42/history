"""List the texts in texts/ with their front matter."""

from __future__ import annotations

from .paths import TEXTS


def front_matter(src: str) -> dict:
    """Flat `key: value` YAML front matter (all reader-md 1 needs)."""
    if not src.startswith("---\n"):
        return {}
    end = src.find("\n---", 4)
    meta = {}
    for line in src[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "#")):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    return meta


def list_texts() -> list[dict]:
    out = []
    for f in sorted(TEXTS.glob("*.md")):
        meta = front_matter(f.read_text(encoding="utf-8"))
        out.append({"id": meta.get("id", f.stem), "title": meta.get("title", f.stem),
                    "subtitle": meta.get("subtitle"), "by": meta.get("translator") or meta.get("author"),
                    "file": f.name})
    return out
