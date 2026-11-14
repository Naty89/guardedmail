/**
 * Record a short spoken question and return it as a small WAV file.
 *
 * Browsers record in different formats (WebM in Chrome, MP4 in Safari). To
 * send the server one format it always understands, the recording is decoded
 * in the browser and re-encoded as 16 kHz mono WAV (about 32 KB per second).
 * The microphone needs HTTPS (or localhost) and the user's permission.
 */

const TARGET_RATE = 16000;
export const MAX_RECORD_SECONDS = 20;

export type Recording = {
  /** Stop recording and get the WAV. */
  stop: () => Promise<Blob>;
  /** Stop and throw the recording away. */
  cancel: () => void;
};

export function canRecord(): boolean {
  return (
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined"
  );
}

/** Ask for the microphone and start recording. Rejects if permission is refused. */
export async function startRecording(): Promise<Recording> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const recorder = new MediaRecorder(stream);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  recorder.start();
  const release = () => stream.getTracks().forEach((track) => track.stop());

  return {
    stop: () =>
      new Promise<Blob>((resolve, reject) => {
        recorder.onstop = () => {
          release();
          toWav(new Blob(chunks, { type: recorder.mimeType })).then(resolve, reject);
        };
        recorder.stop();
      }),
    cancel: () => {
      recorder.onstop = release;
      if (recorder.state !== "inactive") recorder.stop();
      else release();
    },
  };
}

/** Decode any recorded audio and re-encode it as 16 kHz mono 16-bit WAV. */
export async function toWav(recorded: Blob): Promise<Blob> {
  const context = new AudioContext();
  try {
    const decoded = await context.decodeAudioData(await recorded.arrayBuffer());
    const seconds = Math.min(decoded.duration, MAX_RECORD_SECONDS);
    const frames = Math.max(1, Math.floor(seconds * TARGET_RATE));
    // An offline context resamples and mixes down to one channel for us.
    const offline = new OfflineAudioContext(1, frames, TARGET_RATE);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    return encodeWav(rendered.getChannelData(0), TARGET_RATE);
  } finally {
    void context.close();
  }
}

/** Write float samples (-1..1) as a 16-bit PCM WAV file. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true); // size of the format block
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // one channel
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per sample
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}
