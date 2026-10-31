// Parser for reader-md 1 (docs/text-format.md). No dependencies; also runs in Node for tests.

export function frontMatter(src) {
  if (!src.startsWith("---\n")) return { meta: {}, body: src };
  const end = src.indexOf("\n---", 4);
  const meta = {};
  for (const line of src.slice(4, end).split("\n")) {
    const i = line.indexOf(":");
    if (i > 0 && !line.startsWith(" ")) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim().replace(/^["']|["']$/g, "");
  }
  const after = src.indexOf("\n", end + 4);
  return { meta, body: after < 0 ? "" : src.slice(after + 1) };
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function inline(s) {
  return esc(s)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\^\{([^}]*)\}/g, "<sup>$1</sup>")
    .replace(/\^([A-Za-z0-9]+)/g, "<sup>$1</sup>");
}

// Split into groups of consecutive non-blank lines.
function groups(lines) {
  const out = [];
  let cur = [];
  for (const l of lines) {
    if (l.trim() === "") { if (cur.length) out.push(cur), (cur = []); }
    else cur.push(l);
  }
  if (cur.length) out.push(cur);
  return out;
}

const REF = /^\*\*([^*]+)\*\*\s?/;

function paragraph(lines) {
  let text = lines.map((l) => l.replace(/\\$/, "\u0000")).join("\n");
  let ref = null;
  const m = text.match(REF);
  if (m) { ref = m[1]; text = text.slice(m[0].length); }
  const html = inline(text).replace(/\u0000\n?/g, "<br>").replace(/\n/g, " ");
  return { type: "p", ref, html };
}

// Parse the body into blocks. Each block that can be "on screen" gets `ref`
// (its own or, for continuation paragraphs, the previous one) and `heading`.
export function parse(src) {
  const { meta, body } = frontMatter(src);
  const blocks = [];
  let lastRef = null, heading = null, hid = 0;

  const addPara = (p, into) => {
    p.ownRef = p.ref !== null;
    if (p.ref === null) p.ref = lastRef; else lastRef = p.ref;
    p.heading = heading;
    into.push(p);
  };

  for (const g of groups(body.split("\n"))) {
    const h = g[0].match(/^(#{1,6})\s+(.*)$/);
    if (h && g.length === 1) {
      heading = h[2].trim();
      blocks.push({ type: "h", level: h[1].length, text: heading, html: inline(heading), id: `h${++hid}` });
      continue;
    }
    if (g.every((l) => l.startsWith(">"))) {
      const inner = g.map((l) => l.replace(/^> ?/, ""));
      const quote = { type: "quote", label: null, children: [], heading };
      for (const ig of groups(inner)) {
        const lab = ig.length === 1 && ig[0].match(/^\*([^*]+):\*$/);
        if (lab && !quote.label && !quote.children.length) quote.label = lab[1];
        else addPara(paragraph(ig), quote.children);
      }
      blocks.push(quote);
      continue;
    }
    if (g.every((l) => /^[-*] /.test(l))) {
      blocks.push({ type: "ul", items: g.map((l) => inline(l.slice(2))), ref: lastRef, heading });
      continue;
    }
    addPara(paragraph(g), blocks);
  }
  return { meta, blocks };
}
