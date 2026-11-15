/** The in-memory screen state machine. There is no router: App holds one Screen. */
import type { Lang } from "@/i18n";
import type { Letter, Receipt } from "@/lib/api";

export type Screen =
  | "capture"
  | "reading"
  | "explanation"
  | "confirm"
  | "receipt"
  | "scam_blocked"
  | "audit"
  | "history";

export const SCREENS: readonly Screen[] = [
  "capture",
  "reading",
  "explanation",
  "confirm",
  "receipt",
  "scam_blocked",
  "audit",
  "history",
];

export type SampleId = "electric_bill" | "suspicious_letter";

/** What the user picked on the Capture screen. */
/** The most pages one letter can have (the server enforces the same limit). */
export const MAX_PAGES = 4;

export type LetterSource =
  | { kind: "photo"; images: Blob[] } // one Blob per page, in order
  | { kind: "sample"; sampleId: SampleId };

/** Props every screen receives from App. */
export type ScreenProps = {
  lang: Lang;
  go: (screen: Screen) => void;
  source: LetterSource | null;
  /** The result for the current letter, once the server has read it. */
  letter: Letter | null;
  setLetter: (letter: Letter | null) => void;
  /** Set after a confirmed mock payment. */
  receipt: Receipt | null;
  setReceipt: (receipt: Receipt | null) => void;
};
