/**
 * Tiny i18n layer. Every UI string lives in strings.json, keyed by language
 * code and then by string key. There is no i18n library on purpose.
 */
import strings from "./strings.json";

export const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "es", name: "Español" },
  { code: "hi", name: "हिन्दी" },
  { code: "te", name: "తెలుగు" },
  { code: "ta", name: "தமிழ்" },
  { code: "pt", name: "Português" },
  { code: "zh", name: "中文" },
  { code: "ar", name: "العربية" },
  { code: "am", name: "አማርኛ" },
] as const;

export type Lang = (typeof LANGUAGES)[number]["code"];
/** Every key that exists in English. English is the fallback for all others. */
export type StringKey = keyof typeof strings.en;

/** Languages written right to left. */
export const RTL: readonly Lang[] = ["ar"];
/** Languages that have a read-aloud voice (used by the Play button later). */
export const VOICE_ENABLED: readonly Lang[] = ["en", "es", "hi", "te", "ta", "pt"];

export const DEFAULT_LANG: Lang = "en";
const STORAGE_KEY = "guarded.lang";

export function isLang(value: unknown): value is Lang {
  return LANGUAGES.some((language) => language.code === value);
}

export function dirFor(lang: Lang): "rtl" | "ltr" {
  return RTL.includes(lang) ? "rtl" : "ltr";
}

// Invisible Unicode marks that do in plain text what <bdi> does in HTML.
const ISOLATE_START = "⁨";
const ISOLATE_END = "⁩";

/**
 * Translate `key` into `lang`, falling back to English.
 * `vars` fills {placeholders}: t("en", "yes_pay", { amount: "$84.12" }).
 * In right-to-left languages each value is wrapped in isolate marks so an
 * amount or merchant name cannot scramble the order of the sentence.
 */
export function t(lang: Lang, key: StringKey, vars?: Record<string, string | number>): string {
  const table: Partial<Record<StringKey, string>> = strings[lang];
  const template = table[key] ?? strings.en[key] ?? key;
  if (!vars) return template;
  const isolate = RTL.includes(lang);
  return template.replace(/\{(\w+)\}/g, (placeholder, name: string) => {
    if (!(name in vars)) return placeholder;
    const value = String(vars[name]);
    return isolate ? ISOLATE_START + value + ISOLATE_END : value;
  });
}

/** Read the saved language. localStorage can throw (private mode), so guard it. */
export function loadLang(): Lang {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    // Storage unavailable: use the default.
  }
  return DEFAULT_LANG;
}

export function saveLang(lang: Lang): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // Storage unavailable: the choice simply lasts for this visit only.
  }
}
