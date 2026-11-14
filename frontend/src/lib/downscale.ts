/**
 * Shrink a photo in the browser before upload.
 * Phone photos are often 4000px+ and several MB; the reader does not need
 * that, and a small JPEG uploads fast on a weak connection.
 */

type Drawable = { source: CanvasImageSource; width: number; height: number; release: () => void };

/** Decode the file, turning it upright using its EXIF orientation. */
async function decode(file: File): Promise<Drawable> {
  if ("createImageBitmap" in window) {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
      return {
        source: bitmap,
        width: bitmap.width,
        height: bitmap.height,
        release: () => bitmap.close(),
      };
    } catch {
      // Older browsers reject the options argument: fall through to <img>.
    }
  }
  // Fallback: current browsers also apply EXIF orientation to <img> elements.
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return {
      source: img,
      width: img.naturalWidth,
      height: img.naturalHeight,
      release: () => URL.revokeObjectURL(url),
    };
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}

/**
 * Return a JPEG whose long edge is at most `maxEdge` pixels.
 * Small images are never enlarged. Rejects if the file is not a readable image.
 */
export async function downscaleImage(file: File, maxEdge = 1600, quality = 0.85): Promise<Blob> {
  const image = await decode(file);
  try {
    if (!image.width || !image.height) throw new Error("Image has no size");
    const scale = Math.min(1, maxEdge / Math.max(image.width, image.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));

    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas is not available");
    // JPEG has no transparency, so paint white behind see-through images.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image.source, 0, 0, canvas.width, canvas.height);

    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("Could not encode JPEG"))),
        "image/jpeg",
        quality,
      );
    });
  } finally {
    image.release();
  }
}
