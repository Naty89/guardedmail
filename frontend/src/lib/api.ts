/**
 * Backend client. The FastAPI server serves this app and the API from one
 * origin, so every URL is relative ("/health"). No API keys live here.
 *
 * The types below mirror backend/app/schemas.py. Keep them in step by hand.
 * Calls marked "not built yet" have their final URL but the server side
 * arrives in a later milestone.
 */
import type { Lang } from "@/i18n";
import type { LetterSource } from "@/lib/screens";

export type Health = {
  status: string;
  demo_offline?: boolean;
  nessie_configured?: boolean;
  gemini_configured?: boolean;
};

export class ApiError extends Error {
  status: number;
  /** Machine-readable reason from the server, e.g. "image_unreadable". */
  reason: string | null;
  constructor(status: number, message: string, reason: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.reason = reason;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    // Our API answers errors as {"detail": {"error": "<reason id>"}}.
    let reason: string | null = null;
    try {
      const body = await response.json();
      if (typeof body?.detail?.error === "string") reason = body.detail.error;
    } catch {
      // Not JSON: leave the reason empty.
    }
    throw new ApiError(response.status, `${path} failed (${response.status})`, reason);
  }
  return (await response.json()) as T;
}

function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

/** GET /health. Rejects if the backend is down or slower than `timeoutMs`. */
export async function getHealth(timeoutMs = 4000): Promise<Health> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await request<Health>("/health", { signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

/* ------------------------------------------------------------------ */
/* Letters (M4)                                                        */
/* ------------------------------------------------------------------ */

export type ScamSignal =
  | "urgency"
  | "gift_card"
  | "wire"
  | "crypto"
  | "threat"
  | "mismatch_sender"
  | "unknown_payee"
  | "payment_app"
  | "prize"
  | "impersonation"
  | "no_account_number"
  | "embedded_instruction";

export type ScamResult = {
  risk: "low" | "med" | "high";
  reasons: { reason_id: ScamSignal; quote: string }[];
};

/** The single action the server proposes. Payment fields are set only for "pay". */
export type Proposal = {
  id: string;
  action: "pay" | "calendar" | "flag" | "ask_user";
  /** Trusted merchant name from the bank, never text from the letter. */
  payee_name: string | null;
  amount_cents: number | null;
  due_date: string | null;
  expires_at: string | null;
  /** Sent back unchanged with the confirm call. */
  token: string | null;
  /** Why payment is not offered, e.g. "unknown_payee". */
  block_reason: string | null;
};

/** What the reader saw. For display only; it never decides a payment. */
export type LetterSummary = {
  doc_type: string;
  sender: string;
  amount_cents: number | null;
  due_date: string | null;
};

export type Letter = {
  letter_id: string;
  language: Lang;
  explanation: string;
  summary: LetterSummary;
  scam: ScamResult;
  proposal: Proposal;
};

/**
 * POST /letters: multipart form with the language and either the downscaled
 * photo or the id of a built-in sample letter.
 */
export function postLetter(source: LetterSource, language: Lang): Promise<Letter> {
  const form = new FormData();
  form.append("language", language);
  if (source.kind === "photo") form.append("image", source.image, "letter.jpg");
  else form.append("sample", source.sampleId);
  return request<Letter>("/letters", { method: "POST", body: form });
}

/** GET /letters/{id} */
export function getLetter(id: string): Promise<Letter> {
  return request<Letter>(`/letters/${encodeURIComponent(id)}`);
}

/**
 * GET /letters/{id}/calendar.ics: the due date as a calendar file with two
 * reminders. The server refuses it for scam-flagged letters (409).
 */
export function calendarUrl(id: string): string {
  return `/letters/${encodeURIComponent(id)}/calendar.ics`;
}

/** GET /letters/{id}/image: a small picture of the letter for the confirm dialog. */
export function letterImageUrl(id: string): string {
  return `/letters/${encodeURIComponent(id)}/image`;
}

/* ------------------------------------------------------------------ */
/* Payments (M5)                                                       */
/* ------------------------------------------------------------------ */

/** Proof of a mock payment. All fields come from the server's own records. */
export type Receipt = {
  nessie_id: string;
  payee_name: string;
  amount_cents: number;
  new_balance_cents: number;
};
export type ConfirmResult = {
  status: "paid" | "blocked";
  receipt: Receipt | null;
  /** Why nothing was paid, e.g. "token_expired". */
  block_reason: string | null;
};
export type Account = {
  balance_cents: number;
  bills: { bill_id: string; payee: string; amount_cents: number; due_date: string | null; status: string }[];
  recent_payments: { purchase_id: string; merchant_name: string; amount_cents: number; paid_on: string | null }[];
};

/* ------------------------------------------------------------------ */
/* Audit log and judge panel (M7)                                      */
/* ------------------------------------------------------------------ */

export type AuditEvent = {
  seq: number;
  ts: string;
  letter_id: string | null;
  proposal_id: string | null;
  actor: "reader" | "policy" | "user" | "payer";
  event: string;
  prev_hash: string;
  hash: string;
  data: Record<string, unknown>;
};
/** `chain_ok` is false if any event in the whole log was changed or removed. */
export type AuditLog = { events: AuditEvent[]; chain_ok: boolean };

/** GET /audit?letter_id= */
export function getAudit(letterId?: string): Promise<AuditLog> {
  const query = letterId ? `?letter_id=${encodeURIComponent(letterId)}` : "";
  return request<AuditLog>(`/audit${query}`);
}

/** GET /letters/{id}/debug: timings and the policy verdict, for the judge panel. */
export function getLetterDebug(id: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/letters/${encodeURIComponent(id)}/debug`);
}

/**
 * GET /letters/{id}/audio: the explanation read aloud (WAV), or 204 when the
 * server has no audio and the browser's own voice should be used. Never autoplay.
 */
export function letterAudioUrl(id: string): string {
  return `/letters/${encodeURIComponent(id)}/audio`;
}

/**
 * POST /proposals/{id}/confirm with the one-time token from the proposal.
 * Only the token is sent. The server ignores nothing else because it accepts
 * nothing else: the amount and payee are the ones it stored itself.
 */
export function confirmProposal(id: string, token: string): Promise<ConfirmResult> {
  return postJson<ConfirmResult>(`/proposals/${encodeURIComponent(id)}/confirm`, { token });
}

/** POST /proposals/{id}/reject */
export function rejectProposal(id: string): Promise<{ status: string }> {
  return postJson<{ status: string }>(`/proposals/${encodeURIComponent(id)}/reject`);
}

/** GET /account: the mock checking account. */
export function getAccount(): Promise<Account> {
  return request<Account>("/account");
}

/* ------------------------------------------------------------------ */
/* Questions about a letter                                            */
/* ------------------------------------------------------------------ */

export type AskResult = {
  answer_id: number;
  /** What the server heard, or what was typed. */
  question: string;
  answer: string;
  source: "model" | "regenerated" | "fallback";
};

/**
 * POST /letters/{id}/ask with a spoken question (WAV) or a typed one.
 * The answer is text for the screen. Asking can never start a payment.
 */
export function askLetter(id: string, question: Blob | string): Promise<AskResult> {
  const form = new FormData();
  if (typeof question === "string") form.append("question", question);
  else form.append("audio", question, "question.wav");
  return request<AskResult>(`/letters/${encodeURIComponent(id)}/ask`, {
    method: "POST",
    body: form,
  });
}

/** GET /letters/{id}/answers/{n}/audio: an answer read aloud, or 204. */
export function answerAudioUrl(id: string, answerId: number): string {
  return `/letters/${encodeURIComponent(id)}/answers/${answerId}/audio`;
}

/* ------------------------------------------------------------------ */
/* Letter history                                                      */
/* ------------------------------------------------------------------ */

export type HistoryStatus = "paid" | "flagged" | "declined" | "open" | "info";

/** One past letter. Facts are as the reader saw them: display only. */
export type HistoryItem = {
  letter_id: string;
  language: Lang;
  ts: string;
  sender: string;
  doc_type: string;
  amount_cents: number | null;
  due_date: string | null;
  risk: "low" | "med" | "high";
  status: HistoryStatus;
};

/** GET /history: every letter read on this server, newest first. */
export function getHistory(): Promise<{ items: HistoryItem[] }> {
  return request<{ items: HistoryItem[] }>("/history");
}

/** POST /history/{id}/open: reopen an old letter as a fresh result (new proposal if payable). */
export function openHistoryLetter(id: string): Promise<Letter> {
  return postJson<Letter>(`/history/${encodeURIComponent(id)}/open`);
}

