class PcmRingBufferProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.capacity = sampleRate * 4;
    this.buffer = new Float32Array(this.capacity);
    this.readIndex = 0;
    this.writeIndex = 0;
    this.available = 0;
    this.started = false;
    this.startThreshold = Math.floor(sampleRate * 0.08);
    this.targetBuffer = Math.floor(sampleRate * 0.16);
    this.droppedSamples = 0;
    this.underruns = 0;

    this.port.onmessage = (event) => {
      const data = event.data;
      if (data && data.type === 'reset') {
        this.reset();
        return;
      }
      if (!data || data.type !== 'samples') return;
      this.pushSamples(new Float32Array(data.buffer));
    };
  }

  reset() {
    this.readIndex = 0;
    this.writeIndex = 0;
    this.available = 0;
    this.started = false;
  }

  pushSamples(samples) {
    if (this.available + samples.length > this.capacity) {
      const overflow = this.available + samples.length - this.targetBuffer;
      this.dropOldest(Math.max(0, overflow));
    }

    for (let i = 0; i < samples.length; i++) {
      this.buffer[this.writeIndex] = samples[i];
      this.writeIndex = (this.writeIndex + 1) % this.capacity;
    }
    this.available = Math.min(this.capacity, this.available + samples.length);
  }

  dropOldest(count) {
    const drop = Math.min(count, this.available);
    this.readIndex = (this.readIndex + drop) % this.capacity;
    this.available -= drop;
    this.droppedSamples += drop;
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    if (!out) return true;

    if (!this.started) {
      if (this.available < this.startThreshold) {
        out.fill(0);
        return true;
      }
      this.started = true;
    }

    for (let i = 0; i < out.length; i++) {
      if (this.available > 0) {
        out[i] = this.buffer[this.readIndex];
        this.readIndex = (this.readIndex + 1) % this.capacity;
        this.available--;
      } else {
        out[i] = 0;
        this.started = false;
        this.underruns++;
      }
    }

    return true;
  }
}

registerProcessor('pcm-ring-buffer', PcmRingBufferProcessor);
