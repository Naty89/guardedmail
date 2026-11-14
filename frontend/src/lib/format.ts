/** Number helpers. The app always shows Western digits 0-9, in every language. */

// Code point of the digit zero in other scripts (each is followed by 1-9).
const ZEROS = [
  0x0660, // Arabic-Indic
  0x06f0, // Persian
  0x0966, // Devanagari (Hindi)
  0x0be6, // Tamil
  0x0c66, // Telugu
  0xff10, // Fullwidth (Chinese text)
];

/** Replace digits from other scripts with 0-9. "٨٤" -> "84". */
export function toWesternDigits(text: string): string {
  return Array.from(text, (char) => {
    const code = char.codePointAt(0) ?? 0;
    const zero = ZEROS.find((z) => code >= z && code <= z + 9);
    return zero === undefined ? char : String(code - zero);
  }).join("");
}

/** Integer cents -> "$84.12". All money in this app is mock money. */
export function formatCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(Math.round(cents));
  const dollars = Math.floor(abs / 100).toLocaleString("en-US");
  return `${sign}$${dollars}.${String(abs % 100).padStart(2, "0")}`;
}

/** Bytes -> "412 KB" or "1.3 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
