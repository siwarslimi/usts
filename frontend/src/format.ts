import type { Category, Status } from "./types";

// The API stores UTC timestamps without an offset.
export const parseUtc = (s: string) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(s) ? s : `${s}Z`);

export const isoDate = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export const shiftDays = (d: Date, n: number) => {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
};

const sameDay = (a: Date, b: Date) => isoDate(a) === isoDate(b);

/** "14:32", "Hier", "lun. 6", "12 sept." */
export function shortDate(s: string): string {
  const d = parseUtc(s);
  const now = new Date();
  if (sameDay(d, now)) return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  if (sameDay(d, shiftDays(now, -1))) return "Hier";
  if (now.getTime() - d.getTime() < 6 * 86400000) return d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" });
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

export function fullDate(s: string): string {
  return parseUtc(s).toLocaleString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function relative(s: string): string {
  const diff = (Date.now() - parseUtc(s).getTime()) / 1000;
  if (diff < 60) return "à l'instant";
  if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`;
  const days = Math.floor(diff / 86400);
  return `il y a ${days} jour${days > 1 ? "s" : ""}`;
}

export const CATEGORY_LABEL: Record<Category, string> = {
  client: "Client",
  facture: "Facture",
  "rendez-vous": "Rendez-vous",
  newsletter: "Newsletter",
  "spam probable": "Spam probable",
  autre: "Autre",
};
export const CATEGORIES = Object.keys(CATEGORY_LABEL) as Category[];

export const STATUS_LABEL: Record<Status, string> = {
  to_process: "À traiter",
  draft_ready: "Brouillon prêt",
  replied: "Répondu",
  ignored: "Ignoré",
};
export const STATUSES = Object.keys(STATUS_LABEL) as Status[];

export const PRIORITY_LABEL: Record<number, string> = { 1: "Haute", 2: "Moyenne", 3: "Basse" };

export const catClass = (c: string | null) => `cat-${(c || "none").replace(/\s+/g, "-")}`;

export function initials(name: string, email: string): string {
  const src = (name || email).replace(/[^\p{L}\s]/gu, " ").trim();
  const parts = src.split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "?") + (parts[1]?.[0] || "")).toUpperCase();
}

/** Stable pastel hue per sender, used for avatars. */
export function hue(seed: string): number {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}
