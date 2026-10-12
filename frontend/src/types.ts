export type Category = "client" | "facture" | "rendez-vous" | "newsletter" | "spam probable" | "autre";
export type Status = "to_process" | "draft_ready" | "replied" | "ignored";
export type Tone = "formel" | "neutre" | "court";
export type ReplyStatus = "sending" | "sent" | "failed";

export interface User {
  id: number;
  email: string;
}

export interface EmailItem {
  id: number;
  thread_id: number;
  from_name: string;
  from_email: string;
  subject: string;
  snippet: string;
  received_at: string;
  category: Category | null;
  priority: 1 | 2 | 3 | null;
  ai_summary: string | null;
  needs_review: boolean;
  classification_status: "pending" | "done" | "review";
  status: Status;
  thread_size: number;
}

export interface EmailDetail extends EmailItem {
  to: string[];
  cc: string[];
  body_text: string;
  expected_action: string | null;
}

export interface EmailPage {
  items: EmailItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Draft {
  id: number;
  email_id: number;
  tone: Tone;
  body: string;
  source: "ai" | "template";
  created_at: string;
}

export interface Reply {
  id: number;
  email_id: number;
  status: ReplyStatus;
  body: string;
  error: string | null;
  attempts: number;
  created_at: string;
  sent_at: string | null;
}

export interface ThreadMessage {
  kind: "incoming" | "outgoing";
  id: number;
  from_name: string;
  from_email: string;
  to: string[];
  body_text: string;
  at: string;
  status: ReplyStatus | null;
  error: string | null;
}

export interface Thread {
  id: number;
  subject: string;
  messages: ThreadMessage[];
  emails: EmailDetail[];
  latest_draft: Draft | null;
  replies: Reply[];
}

export interface Summary {
  date: string;
  received: number;
  by_category: Record<string, number>;
  by_status: Record<Status, number>;
  to_review: number;
  text: string;
  text_source: "ai" | "template";
  top: { email: EmailItem; score: number; reasons: string[] }[];
}

export interface Counts {
  total: number;
  status: Partial<Record<Status, number>>;
  category_open: Record<string, number>;
  to_review: number;
}

export interface Filters {
  status: Status[];
  category: Category[];
  priority: number[];
  sender: string;
  q: string;
  period: "all" | "today" | "7d" | "30d" | "custom";
  date_from: string;
  date_to: string;
  needs_review: boolean;
}

export const EMPTY_FILTERS: Filters = {
  status: [],
  category: [],
  priority: [],
  sender: "",
  q: "",
  period: "all",
  date_from: "",
  date_to: "",
  needs_review: false,
};
