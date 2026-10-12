import type { Counts, Draft, EmailDetail, EmailPage, Filters, Reply, Status, Summary, Thread, Tone, User } from "./types";
import { isoDate, shiftDays } from "./format";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => (onUnauthorized = fn);

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (res.status === 401 && !path.startsWith("/auth/login")) onUnauthorized();
  if (!res.ok) {
    let message = `Erreur ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export function filtersToQuery(f: Filters, page: number, pageSize = 25): string {
  const p = new URLSearchParams();
  f.status.forEach((s) => p.append("status", s));
  f.category.forEach((c) => p.append("category", c));
  f.priority.forEach((x) => p.append("priority", String(x)));
  if (f.sender.trim()) p.set("sender", f.sender.trim());
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.needs_review) p.set("needs_review", "true");
  const today = new Date();
  if (f.period === "today") p.set("date_from", isoDate(today));
  if (f.period === "7d") p.set("date_from", isoDate(shiftDays(today, -6)));
  if (f.period === "30d") p.set("date_from", isoDate(shiftDays(today, -29)));
  if (f.period === "custom") {
    if (f.date_from) p.set("date_from", f.date_from);
    if (f.date_to) p.set("date_to", f.date_to);
  }
  p.set("page", String(page));
  p.set("page_size", String(pageSize));
  return p.toString();
}

export const api = {
  login: (email: string, password: string) =>
    request<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<User>("/auth/me"),

  emails: (f: Filters, page: number) => request<EmailPage>(`/emails?${filtersToQuery(f, page)}`),
  counts: () => request<Counts>("/emails/counts"),
  senders: () => request<{ email: string; name: string; count: number }[]>("/emails/senders"),
  setStatus: (id: number, status: Status) =>
    request<EmailDetail>(`/emails/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  thread: (id: number) => request<Thread>(`/threads/${id}`),
  summary: (date?: string) => request<Summary>(`/summary${date ? `?date=${date}` : ""}`),

  draft: (emailId: number, tone: Tone) =>
    request<Draft>(`/emails/${emailId}/draft`, { method: "POST", body: JSON.stringify({ tone }) }),
  reply: (emailId: number, body: string, idempotencyKey: string, draftId?: number) =>
    request<Reply>(`/emails/${emailId}/reply`, {
      method: "POST",
      body: JSON.stringify({ body, draft_id: draftId ?? null }),
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  retry: (replyId: number) => request<Reply>(`/replies/${replyId}/retry`, { method: "POST" }),
};

export function newIdempotencyKey(): string {
  // randomUUID only exists in secure contexts (https or localhost)
  if (typeof crypto.randomUUID === "function" && window.isSecureContext) return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
