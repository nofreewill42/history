import { parse, inline } from "./readermd.js";

const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const CHUNK_S = 5;          // audio upload interval
const NAV_SETTLE_MS = 350;  // log a position once scrolling settles
const READING_LINE = 0.3;   // fraction of the reader's height that counts as "on screen"

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: opts.body && !(opts.body instanceof ArrayBuffer) ? { "Content-Type": "application/json" } : opts.headers,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `${res.status} ${res.statusText}`);
  return data;
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body ?? {}) });

function say(msg, warn = false) {
  const el = $("#status");
  el.textContent = msg;
  el.title = msg;
  el.classList.toggle("warn", warn);
}

const fmtTime = (s) => {
  s = Math.floor(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
};

// --- texts ----------------------------------------------------------------------

let texts = [];
let current = { id: null, navEls: [], headingOf: [], tocLinks: new Map() };

function render(id, src) {
  const { blocks } = parse(src);
  const article = $("#text");
  const toc = $("#toc");
  article.replaceChildren();
  toc.replaceChildren();
  const navEls = [], headingOf = [], tocLinks = new Map();
  let lastHeadingEl = null;

  const passage = (p, parent) => {
    const el = document.createElement("p");
    el.className = "passage";
    if (p.ownRef) {
      const a = document.createElement("a");
      a.className = "ref";
      a.href = `#${id}/${p.ref}`;
      a.textContent = p.ref;
      a.id = `ref-${p.ref}`;
      el.append(a);
    }
    el.insertAdjacentHTML("beforeend", p.html);
    el.dataset.ref = p.ref ?? "";
    el.dataset.heading = p.heading ?? "";
    parent.append(el);
    navEls.push(el);
    headingOf.push(lastHeadingEl);
  };

  for (const b of blocks) {
    if (b.type === "h") {
      const el = document.createElement(`h${b.level}`);
      el.id = b.id;
      el.innerHTML = b.html;
      el.dataset.heading = b.text;
      article.append(el);
      navEls.push(el);
      headingOf.push(el);
      lastHeadingEl = el;
      const a = document.createElement("a");
      a.href = `#${id}/${b.id}`;
      a.className = `l${b.level}`;
      a.innerHTML = b.html;
      toc.append(a);
      tocLinks.set(el, a);
    } else if (b.type === "quote") {
      const box = document.createElement("div");
      box.className = "version";
      if (b.label) {
        const l = document.createElement("p");
        l.className = "label";
        l.innerHTML = inline(b.label);
        box.append(l);
      }
      b.children.forEach((c) => passage(c, box));
      article.append(box);
    } else if (b.type === "ul") {
      const ul = document.createElement("ul");
      ul.innerHTML = b.items.map((i) => `<li>${i}</li>`).join("");
      article.append(ul);
    } else {
      passage(b, article);
    }
  }
  current = { id, navEls, headingOf, tocLinks, here: null, lastLogged: null };
}

async function openText(id, target) {
  if (current.id !== id) {
    const meta = texts.find((t) => t.id === id);
    if (!meta) return say(`No text with id ${id}`, true);
    const src = await (await fetch(`/texts/${meta.file}`)).text();
    render(id, src);
    $("#text-select").value = id;
    document.title = `${meta.title} | History reader`;
  }
  const el = target && (document.getElementById(target.startsWith("h") && !target.includes(":") ? target : `ref-${target}`));
  const reader = $("#reader");
  if (el) {
    const block = el.closest(".passage") || el;
    reader.scrollTop += block.getBoundingClientRect().top - reader.getBoundingClientRect().top - reader.clientHeight * READING_LINE + 4;
  } else if (!target) {
    reader.scrollTop = 0;
  }
  updatePosition(true);
}

// --- where am I? ----------------------------------------------------------------

function elementAtReadingLine() {
  const reader = $("#reader");
  const line = reader.getBoundingClientRect().top + reader.clientHeight * READING_LINE;
  const els = current.navEls;
  let lo = 0, hi = els.length - 1, found = 0;
  while (lo <= hi) {  // last element whose top is above the reading line
    const mid = (lo + hi) >> 1;
    if (els[mid].getBoundingClientRect().top <= line) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}

let settleTimer = null;
function updatePosition(immediate = false) {
  if (!current.navEls.length) return;
  const i = elementAtReadingLine();
  const el = current.navEls[i];
  if (current.here !== el) {
    current.here?.classList.remove("here");
    (current.here?.closest(".version"))?.classList.remove("here");
    el.classList.add("here");
    current.here = el;
    const h = current.headingOf[i];
    current.tocLinks.forEach((a) => a.removeAttribute("aria-current"));
    const link = h && current.tocLinks.get(h);
    if (link) {
      link.setAttribute("aria-current", "true");
      link.scrollIntoView({ block: "nearest" });
    }
  }
  clearTimeout(settleTimer);
  settleTimer = setTimeout(() => logPosition(el), immediate ? 0 : NAV_SETTLE_MS);
}

function logPosition(el) {
  const isHeading = /^H\d$/.test(el.tagName);
  const ref = isHeading ? null : (el.dataset.ref || null);
  const heading = el.dataset.heading || null;
  const key = `${current.id}|${ref}|${heading}`;
  if (key === current.lastLogged) return;
  current.lastLogged = key;
  history.replaceState(null, "", `#${current.id}/${ref ?? (isHeading ? el.id : "")}`);
  if (rec) navEvent({ text: current.id, ref, heading });
}

// --- recording ------------------------------------------------------------------

let rec = null;

function navEvent(ev) {
  const e = { t: rec.samples / rec.rate, ...ev };
  post(`/api/sessions/${rec.sid}/nav`, [e]).catch((err) => say(`Position not logged: ${err.message}`, true));
}

function enqueueChunk() {
  if (!rec.pending.length) return;
  const n = rec.pending.reduce((a, b) => a + b.length, 0);
  const data = new Int16Array(n);
  let o = 0;
  for (const p of rec.pending) { data.set(p, o); o += p.length; }
  rec.pending = [];
  rec.pendingSamples = 0;
  rec.queue.push({ seq: rec.seq++, data });
  pump();
}

async function pump() {
  if (rec.sending) return;
  rec.sending = true;
  const r = rec;
  while (r.queue.length) {
    const { seq, data } = r.queue[0];
    try {
      await api(`/api/sessions/${r.sid}/audio?seq=${seq}`, {
        method: "POST", body: data.buffer, headers: { "Content-Type": "application/octet-stream" },
      });
      r.queue.shift();
      if (r.retrying) { r.retrying = false; say("Upload caught up."); }
    } catch (err) {
      r.retrying = true;
      const waiting = r.queue.reduce((a, c) => a + c.data.length, 0) / r.rate;
      say(`${Math.round(waiting)} s of audio not saved yet (${err.message}). Retrying…`, true);
      await sleep(2000);
    }
  }
  r.sending = false;
}

async function startRecording() {
  const btn = $("#rec");
  btn.disabled = true;
  say("Asking for the microphone…");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    const ctx = new AudioContext();
    await ctx.audioWorklet.addModule("recorder-worklet.js");
    const mic = stream.getAudioTracks()[0]?.label || "";
    const session = await post("/api/sessions", { sample_rate: ctx.sampleRate, mic, live: $("#live-toggle").checked });
    rec = { sid: session.id, ctx, stream, rate: ctx.sampleRate, samples: 0, pending: [], pendingSamples: 0,
            seq: 0, queue: [], sending: false, retrying: false };
    const node = new AudioWorkletNode(ctx, "pcm-recorder");
    const mute = ctx.createGain();
    mute.gain.value = 0;
    const source = ctx.createMediaStreamSource(stream);
    source.connect(node).connect(mute).connect(ctx.destination);
    rec.source = source;
    rec.node = node;
    node.port.onmessage = ({ data }) => {
      if (!rec) return;
      const pcm = new Int16Array(data.pcm);
      rec.pending.push(pcm);
      rec.pendingSamples += pcm.length;
      rec.samples += pcm.length;
      $("#meter span").style.width = `${Math.min(100, Math.sqrt(data.peak) * 100)}%`;
      if (rec.pendingSamples >= rec.rate * CHUNK_S) enqueueChunk();
    };
    rec.clock = setInterval(() => { $("#clock").textContent = fmtTime(rec.samples / rec.rate); }, 250);
    document.body.classList.add("recording");
    btn.setAttribute("aria-pressed", "true");
    btn.querySelector(".rec-label").textContent = "Stop";
    say(`Recording session ${session.id}`);
    current.lastLogged = null;
    if (current.here) logPosition(current.here);
    if ($("#live-toggle").checked) pollLive();
  } catch (err) {
    say(`Could not start recording: ${err.message}`, true);
    rec = null;
  } finally {
    btn.disabled = false;
  }
}

async function stopRecording() {
  const btn = $("#rec");
  btn.disabled = true;
  const r = rec;
  say("Saving the last seconds…");
  r.source.disconnect();
  r.stream.getTracks().forEach((t) => t.stop());
  await sleep(300);  // let the worklet deliver its last buffer
  await r.ctx.close();
  enqueueChunk();
  while (r.queue.length || r.sending) await sleep(200);
  clearInterval(r.clock);
  rec = null;
  document.body.classList.remove("recording");
  btn.setAttribute("aria-pressed", "false");
  btn.querySelector(".rec-label").textContent = "Record";
  $("#meter span").style.width = "0";
  $("#preview").textContent = "";
  try {
    say("Encoding and committing…");
    const report = await post(`/api/sessions/${r.sid}/stop`, {});
    const done = `Saved ${r.sid} (${fmtTime(report.session.duration_s)})` + (report.commit ? `, committed ${report.commit}.` : ".");
    say(report.warning ? `${done} ${report.warning}` : done, Boolean(report.warning));
    if (report.job) watchJobs();
  } catch (err) {
    say(`Stopping failed: ${err.message}. The audio is on disk; restart the studio to finish the session.`, true);
  } finally {
    btn.disabled = false;
  }
}

// Keep the newest words visible: trim from the front to what fits.
function showPreview(text) {
  const el = $("#preview");
  el.textContent = text;
  let cut = 0;
  while (el.scrollWidth > el.clientWidth && cut < text.length) {
    cut = text.indexOf(" ", cut + 1);
    if (cut < 0) break;
    el.textContent = "…" + text.slice(cut);
  }
}

async function pollLive() {
  while (rec && $("#live-toggle").checked) {
    try {
      const l = await api("/api/live");
      showPreview(l.error ? `Live preview: ${l.error}` : l.text);
    } catch { /* studio busy; try again */ }
    await sleep(2000);
  }
  $("#preview").textContent = "";
}

// --- jobs -------------------------------------------------------------------------

let watching = false;
async function watchJobs() {
  if (watching) return;
  watching = true;
  try {
    while (true) {
      const jobs = await api("/api/jobs");
      renderJobs(jobs);
      const active = jobs.filter((j) => j.state === "queued" || j.state === "running");
      if (!rec) {
        const j = active[0] || jobs[0];
        if (j) {
          if (j.state === "running") say(`Transcribing ${j.session} with ${j.model}: ${Math.round(j.progress * 100)}%`);
          else if (j.state === "queued") say(`Waiting to transcribe ${j.session}`);
          else if (j.state === "done") say(`Transcribed ${j.session} with ${j.model}` + (j.commit ? `, committed ${j.commit}.` : ".") + (j.note ? ` ${j.note}` : ""));
          else say(`Transcription of ${j.session} failed: ${j.error}`, true);
        }
      }
      if (!active.length) break;
      await sleep(1500);
    }
  } finally {
    watching = false;
  }
  if ($("#sessions-dialog").open) loadSessions();
}

function renderJobs(jobs) {
  const box = $("#jobs");
  box.replaceChildren(...jobs.slice(0, 5).map((j) => {
    const p = document.createElement("p");
    const what = `${j.session} with ${j.model}`;
    if (j.state === "running") p.innerHTML = `Transcribing ${what} <progress max="1" value="${j.progress}"></progress>`;
    else if (j.state === "queued") p.textContent = `Waiting: ${what}`;
    else if (j.state === "done") p.textContent = `Done: ${what}${j.commit ? ` (commit ${j.commit})` : ""}${j.note ? `. ${j.note}` : ""}`;
    else { p.textContent = `Failed: ${what}: ${j.error}`; p.className = "state-missing"; }
    return p;
  }));
}

// --- models panel ------------------------------------------------------------------

let modelsTimer = null;

function sizeLabel(n) {
  if (!n) return "";
  return n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.round(n / 1e6)} MB`;
}

async function loadModels() {
  const { models, settings } = await api("/api/models");
  const tbody = $("#models-table tbody");
  tbody.replaceChildren(...models.map((m) => {
    const tr = document.createElement("tr");
    const s = m.status;
    let state;
    if (s.engine_missing.length) state = `<span class="state-missing">Engine not installed</span><span class="sub">Run <code>uv sync --extra ${s.engine_extra}</code> and restart the studio</span>`;
    else if (s.download?.state === "downloading") {
      const pct = s.download.total ? ` ${Math.round((100 * s.download.done) / s.download.total)}%` : "";
      state = `Downloading${pct}<span class="sub">${sizeLabel(s.download.done)}${s.download.total ? ` of ${sizeLabel(s.download.total)}` : ""}</span>`;
    } else if (s.download?.state === "error") state = `<span class="state-missing">Download failed</span><span class="sub">${s.download.error}</span>`;
    else if (s.installed) state = `<span class="state-ready">Ready</span>`;
    else state = "Not downloaded";
    const langs = m.english_only ? "English" : m.languages.length > 4 ? `${m.languages.length} languages` : m.languages.join(", ");
    const radio = (name) => `<input type="radio" name="${name}" value="${m.id}" aria-label="${name === "live_model" ? "Live" : "Final"}: ${m.name}" ${settings[name] === m.id ? "checked" : ""}>`;
    const downloading = s.download?.state === "downloading";
    const action = m.local ? "<span class='sub'>local checkpoint</span>"
      : s.installed ? `<button class="act" data-delete="${m.id}">Delete</button>`
      : `<button class="act" data-install="${m.id}" ${downloading ? "disabled" : ""}>Install</button>`;
    tr.innerHTML = `
      <td><strong>${m.name}</strong><span class="sub">${m.hf_repo}</span><span class="sub">engine: ${m.engine}</span></td>
      <td>${m.params}<span class="sub">~${m.vram_gb} GB VRAM</span></td>
      <td>${langs}${m.word_timestamps ? "" : "<span class='sub'>no word timestamps</span>"}</td>
      <td>${state}</td>
      <td>${radio("live_model")}</td>
      <td>${radio("final_model")}</td>
      <td>${action}</td>`;
    tr.title = m.notes || "";
    return tr;
  }));
  return models;
}

async function openModels() {
  $("#models-dialog").showModal();
  await loadModels();
  clearInterval(modelsTimer);
  modelsTimer = setInterval(() => { if ($("#models-dialog").open) loadModels(); else clearInterval(modelsTimer); }, 1500);
}

$("#models-table").addEventListener("click", async (e) => {
  const install = e.target.dataset.install, del = e.target.dataset.delete;
  try {
    if (install) { e.target.disabled = true; await post(`/api/models/${install}/install`); }
    if (del && confirm(`Delete the downloaded weights of ${del}? You can install them again later.`)) {
      await api(`/api/models/${del}`, { method: "DELETE" });
    }
    await loadModels();
  } catch (err) { say(err.message, true); }
});

$("#models-table").addEventListener("change", async (e) => {
  if (e.target.type !== "radio") return;
  try {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ [e.target.name]: e.target.value }) });
    say(`${e.target.name === "live_model" ? "Live" : "Final"} model set to ${e.target.value}.`);
  } catch (err) { say(err.message, true); }
});

// --- sessions panel -----------------------------------------------------------------

async function loadSessions() {
  const [list, { models, settings }] = await Promise.all([api("/api/sessions"), api("/api/models")]);
  const ready = models.filter((m) => m.status.installed && !m.status.engine_missing.length);
  const tbody = $("#sessions-table tbody");
  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="5">No sessions yet. Press Record to start one.</td></tr>`;
    return;
  }
  const options = ready.map((m) => `<option value="${m.id}" ${m.id === settings.final_model ? "selected" : ""}>${m.name}</option>`).join("");
  tbody.replaceChildren(...list.map((s) => {
    const tr = document.createElement("tr");
    const run = !ready.length ? "<span class='sub'>Install a model first</span>"
      : !s.has_original && !s.has_audio ? "<span class='sub'>Audio not on this computer (git lfs pull)</span>"
      : `<select aria-label="Model for ${s.id}">${options}</select> <button class="act" data-run="${s.id}">Transcribe</button>`;
    tr.innerHTML = `
      <td><strong>${s.id}</strong><span class="sub">${s.notes || ""}</span></td>
      <td>${fmtTime(s.duration_s)}</td>
      <td>${s.texts.join(", ") || "none"}</td>
      <td>${s.asr.join(", ") || "not yet"}</td>
      <td>${run}</td>`;
    return tr;
  }));
}

$("#sessions-table").addEventListener("click", async (e) => {
  const sid = e.target.dataset.run;
  if (!sid) return;
  const model = e.target.previousElementSibling.value;
  try {
    await post(`/api/sessions/${sid}/transcribe`, { model });
    watchJobs();
  } catch (err) { say(err.message, true); }
});

// --- wiring --------------------------------------------------------------------------

$("#rec").addEventListener("click", () => (rec ? stopRecording() : startRecording()));
$("#live-toggle").addEventListener("change", async (e) => {
  if (!rec) return;
  await post(`/api/sessions/${rec.sid}/live`, { enabled: e.target.checked }).catch((err) => say(err.message, true));
  if (e.target.checked) pollLive();
});
$("#open-models").addEventListener("click", openModels);
$("#open-sessions").addEventListener("click", async () => {
  $("#sessions-dialog").showModal();
  await loadSessions();
  renderJobs(await api("/api/jobs"));
});
document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
$("#text-select").addEventListener("change", (e) => { location.hash = `#${e.target.value}/`; });
$("#reader").addEventListener("scroll", () => requestAnimationFrame(() => updatePosition()), { passive: true });
$("#toc-toggle").addEventListener("click", () => {
  const open = $("#sidebar").classList.toggle("open");
  $("#toc-toggle").setAttribute("aria-expanded", String(open));
});
$("#toc").addEventListener("click", () => $("#sidebar").classList.remove("open"));
window.addEventListener("hashchange", fromHash);
window.addEventListener("beforeunload", (e) => { if (rec) e.preventDefault(); });

function fromHash() {
  const [id, target] = decodeURIComponent(location.hash.slice(1)).split(/\/(.*)/s);
  if (id) openText(id, target || null);
  else if (texts[0]) openText(texts[0].id, null);
}

async function init() {
  try {
    texts = await api("/api/texts");
  } catch (err) {
    say(`Can't reach the studio: ${err.message}. Start it with: uv run studio`, true);
    return;
  }
  $("#text-select").innerHTML = texts.map((t) => `<option value="${t.id}">${t.title}${t.subtitle ? ` (${t.subtitle})` : ""}</option>`).join("");
  fromHash();
  const st = await api("/api/status");
  const notes = [];
  if (!st.ffmpeg) notes.push("ffmpeg is missing, so recordings can't be encoded.");
  if (st.lfs_problem) notes.push(`Recordings won't be committed: ${st.lfs_problem}.`);
  if (!st.settings.final_model) notes.push("Choose a final model in Models to get transcripts.");
  for (const r of st.recovered) notes.push(`Recovered interrupted session ${r.session.id}.`);
  if (notes.length) say(notes.join(" "), Boolean(st.lfs_problem || !st.ffmpeg));
  watchJobs();
}
init();
