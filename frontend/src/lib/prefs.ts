/**
 * Display preferences: text size and contrast. Saved on this device only.
 * They are applied as attributes on <html>, and index.css does the rest.
 */

export type TextSize = "normal" | "large" | "xlarge";
export type Contrast = "standard" | "high";
export type Prefs = { size: TextSize; contrast: Contrast };

const STORAGE_KEY = "guarded.display";
export const TEXT_SIZES: readonly TextSize[] = ["normal", "large", "xlarge"];
export const CONTRASTS: readonly Contrast[] = ["standard", "high"];

/** First visit: follow the phone's own "increase contrast" setting if it is on. */
function defaultPrefs(): Prefs {
  let contrast: Contrast = "standard";
  try {
    if (window.matchMedia("(prefers-contrast: more)").matches) contrast = "high";
  } catch {
    // Old browser: keep the standard colours.
  }
  return { size: "normal", contrast };
}

export function loadPrefs(): Prefs {
  const fallback = defaultPrefs();
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null");
    return {
      size: TEXT_SIZES.includes(saved?.size) ? saved.size : fallback.size,
      contrast: CONTRASTS.includes(saved?.contrast) ? saved.contrast : fallback.contrast,
    };
  } catch {
    return fallback; // storage blocked or damaged: use the defaults
  }
}

export function savePrefs(prefs: Prefs): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Not saved: the choice lasts for this visit only.
  }
}

/** Put the preferences on <html> so the stylesheet can react to them. */
export function applyPrefs(prefs: Prefs): void {
  document.documentElement.dataset.text = prefs.size;
  document.documentElement.dataset.contrast = prefs.contrast;
}
