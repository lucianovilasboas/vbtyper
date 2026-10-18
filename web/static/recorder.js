// Envoltório do MediaRecorder: abre o microfone, grava e devolve um Blob.

const PREFERRED_TYPES = [
  "audio/webm;codecs=opus",
  "audio/ogg;codecs=opus",
  "audio/webm",
  "audio/ogg",
];

export class Recorder {
  #stream = null;
  #recorder = null;
  #chunks = [];
  #stopped = null;

  static get supported() {
    return Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  }

  get recording() {
    return this.#recorder?.state === "recording";
  }

  get stream() {
    return this.#stream;
  }

  async open() {
    this.#stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
    this.#recorder = mimeType
      ? new MediaRecorder(this.#stream, { mimeType })
      : new MediaRecorder(this.#stream);
    this.#chunks = [];
    this.#recorder.ondataavailable = (event) => {
      if (event.data && event.data.size) this.#chunks.push(event.data);
    };
    this.#stopped = new Promise((resolve, reject) => {
      this.#recorder.onstop = () =>
        resolve(new Blob(this.#chunks, { type: this.#recorder.mimeType || "audio/webm" }));
      this.#recorder.onerror = () =>
        reject(new Error("Falha ao gravar áudio."));
    });
  }

  begin() {
    this.#recorder.start();
  }

  async finish() {
    if (!this.#recorder || this.#recorder.state === "inactive") {
      this.#release();
      return new Blob(this.#chunks, { type: "audio/webm" });
    }
    this.#recorder.stop();
    try {
      return await this.#stopped;
    } finally {
      this.#release();
    }
  }

  cancel() {
    try {
      if (this.#recorder && this.#recorder.state !== "inactive") this.#recorder.stop();
    } catch {
      /* já parado */
    }
    this.#release();
  }

  #release() {
    if (this.#stream) {
      this.#stream.getTracks().forEach((track) => track.stop());
      this.#stream = null;
    }
  }
}
