// Runs on the audio thread. Converts the first input channel to 16-bit PCM and
// posts it to the page about every 0.25 s, together with the peak level.
class PcmRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Int16Array(Math.round(sampleRate / 4));
    this.n = 0;
    this.peak = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) {
        const v = Math.max(-1, Math.min(1, ch[i]));
        this.peak = Math.max(this.peak, Math.abs(v));
        this.buf[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        if (this.n === this.buf.length) this.flush();
      }
    }
    return true;
  }
  flush() {
    const out = this.buf.slice(0, this.n);
    this.port.postMessage({ pcm: out.buffer, peak: this.peak }, [out.buffer]);
    this.n = 0;
    this.peak = 0;
  }
}
registerProcessor("pcm-recorder", PcmRecorder);
