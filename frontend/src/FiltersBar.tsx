import { useEffect, useState } from "react";
import { AlertTriangle, Calendar, ChevronDown, Flag, Layers, ListChecks, Menu, Search, User as UserIcon, X } from "lucide-react";
import { api } from "./api";
import { CATEGORIES, CATEGORY_LABEL, PRIORITY_LABEL, STATUSES, STATUS_LABEL, catClass } from "./format";
import type { Filters } from "./types";
import { EMPTY_FILTERS } from "./types";
import { Popover } from "./ui";

const PERIODS: { id: Filters["period"]; label: string }[] = [
  { id: "all", label: "Toutes les dates" },
  { id: "today", label: "Aujourd'hui" },
  { id: "7d", label: "7 derniers jours" },
  { id: "30d", label: "30 derniers jours" },
  { id: "custom", label: "Personnalisée…" },
];

function toggle<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export function title(f: Filters): string {
  if (f.needs_review) return "À vérifier";
  if (f.status.length === 1 && !f.category.length) return STATUS_LABEL[f.status[0]];
  if (f.category.length === 1 && !f.status.length) return CATEGORY_LABEL[f.category[0]];
  return JSON.stringify(f) === JSON.stringify(EMPTY_FILTERS) ? "Tous les e-mails" : "Résultats filtrés";
}

export function FiltersBar({ filters, onChange, total, onMenu }: { filters: Filters; onChange: (f: Filters) => void; total: number | null; onMenu: () => void }) {
  const [q, setQ] = useState(filters.q);
  const [senders, setSenders] = useState<{ email: string; name: string; count: number }[]>([]);
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });

  useEffect(() => setQ(filters.q), [filters.q]);
  useEffect(() => {
    if (q === filters.q) return;
    const t = setTimeout(() => set({ q }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const active = JSON.stringify({ ...filters, q: "" }) !== JSON.stringify({ ...EMPTY_FILTERS, q: "" });
  const periodLabel =
    filters.period === "custom" && (filters.date_from || filters.date_to)
      ? `${filters.date_from || "…"} → ${filters.date_to || "…"}`
      : PERIODS.find((p) => p.id === filters.period)!.label;

  return (
    <div className="filters">
      <div className="filters-top">
        <button className="icon-btn only-mobile" onClick={onMenu} aria-label="Menu">
          <Menu size={20} />
        </button>
        <h1 className="list-title">
          {title(filters)}
          {total !== null && <span className="list-count">{total}</span>}
        </h1>
      </div>

      <label className="search">
        <Search size={16} />
        <input
          placeholder="Rechercher dans l'objet et le contenu…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Recherche"
        />
        {q && (
          <button className="icon-btn icon-btn-sm" onClick={() => (setQ(""), set({ q: "" }))} aria-label="Effacer la recherche">
            <X size={14} />
          </button>
        )}
      </label>

      <div className="chips">
        <Popover
          trigger={(open, t) => (
            <button className={`chip ${filters.category.length ? "on" : ""} ${open ? "open" : ""}`} onClick={t}>
              <Layers size={14} />
              {filters.category.length ? filters.category.map((c) => CATEGORY_LABEL[c]).join(", ") : "Catégorie"}
              <ChevronDown size={14} />
            </button>
          )}
        >
          {() => (
            <div className="menu">
              {CATEGORIES.map((c) => (
                <label key={c} className="menu-check">
                  <input type="checkbox" checked={filters.category.includes(c)} onChange={() => set({ category: toggle(filters.category, c) })} />
                  <span className={`cat-swatch ${catClass(c)}`} />
                  {CATEGORY_LABEL[c]}
                </label>
              ))}
            </div>
          )}
        </Popover>

        <Popover
          trigger={(open, t) => (
            <button className={`chip ${filters.priority.length ? "on" : ""} ${open ? "open" : ""}`} onClick={t}>
              <Flag size={14} />
              {filters.priority.length ? [...filters.priority].sort().map((p) => PRIORITY_LABEL[p]).join(", ") : "Priorité"}
              <ChevronDown size={14} />
            </button>
          )}
        >
          {() => (
            <div className="menu">
              {[1, 2, 3].map((p) => (
                <label key={p} className="menu-check">
                  <input type="checkbox" checked={filters.priority.includes(p)} onChange={() => set({ priority: toggle(filters.priority, p) })} />
                  <span className={`prio prio-${p}`}>
                    <span className="bars">
                      <i />
                      <i />
                      <i />
                    </span>
                  </span>
                  {PRIORITY_LABEL[p]}
                </label>
              ))}
            </div>
          )}
        </Popover>

        <Popover
          trigger={(open, t) => (
            <button className={`chip ${filters.status.length ? "on" : ""} ${open ? "open" : ""}`} onClick={t}>
              <ListChecks size={14} />
              {filters.status.length ? filters.status.map((s) => STATUS_LABEL[s]).join(", ") : "Statut"}
              <ChevronDown size={14} />
            </button>
          )}
        >
          {() => (
            <div className="menu">
              {STATUSES.map((s) => (
                <label key={s} className="menu-check">
                  <input type="checkbox" checked={filters.status.includes(s)} onChange={() => set({ status: toggle(filters.status, s) })} />
                  <span className={`status-dot status-${s}`} />
                  {STATUS_LABEL[s]}
                </label>
              ))}
            </div>
          )}
        </Popover>

        <Popover
          trigger={(open, t) => (
            <button
              className={`chip ${filters.sender ? "on" : ""} ${open ? "open" : ""}`}
              onClick={() => {
                if (!senders.length) api.senders().then(setSenders).catch(() => {});
                t();
              }}
            >
              <UserIcon size={14} />
              {filters.sender || "Expéditeur"}
              <ChevronDown size={14} />
            </button>
          )}
        >
          {(close) => <SenderMenu value={filters.sender} senders={senders} onPick={(s) => (set({ sender: s }), close())} />}
        </Popover>

        <Popover
          trigger={(open, t) => (
            <button className={`chip ${filters.period !== "all" ? "on" : ""} ${open ? "open" : ""}`} onClick={t}>
              <Calendar size={14} />
              {periodLabel}
              <ChevronDown size={14} />
            </button>
          )}
          align="right"
        >
          {(close) => (
            <div className="menu">
              {PERIODS.map((p) => (
                <button
                  key={p.id}
                  className={`menu-item ${filters.period === p.id ? "selected" : ""}`}
                  onClick={() => {
                    set({ period: p.id });
                    if (p.id !== "custom") close();
                  }}
                >
                  {p.label}
                </button>
              ))}
              {filters.period === "custom" && (
                <div className="menu-dates">
                  <label>
                    Du
                    <input type="date" value={filters.date_from} max={filters.date_to || undefined} onChange={(e) => set({ date_from: e.target.value })} />
                  </label>
                  <label>
                    Au
                    <input type="date" value={filters.date_to} min={filters.date_from || undefined} onChange={(e) => set({ date_to: e.target.value })} />
                  </label>
                </div>
              )}
            </div>
          )}
        </Popover>

        <button className={`chip ${filters.needs_review ? "on warn" : ""}`} onClick={() => set({ needs_review: !filters.needs_review })}>
          <AlertTriangle size={14} />À vérifier
        </button>

        {active && (
          <button className="chip chip-reset" onClick={() => onChange({ ...EMPTY_FILTERS, q: filters.q })}>
            <X size={14} />
            Réinitialiser
          </button>
        )}
      </div>
    </div>
  );
}

function SenderMenu({ value, senders, onPick }: { value: string; senders: { email: string; name: string; count: number }[]; onPick: (s: string) => void }) {
  const [text, setText] = useState(value);
  const list = senders.filter((s) => `${s.name} ${s.email}`.toLowerCase().includes(text.toLowerCase())).slice(0, 8);
  return (
    <div className="menu menu-wide">
      <form onSubmit={(e) => (e.preventDefault(), onPick(text.trim()))}>
        <input className="menu-input" autoFocus placeholder="Nom ou adresse…" value={text} onChange={(e) => setText(e.target.value)} />
      </form>
      {list.map((s) => (
        <button key={s.email} className="menu-item sender-item" onClick={() => onPick(s.email)}>
          <span>
            {s.name || s.email}
            <small>{s.email}</small>
          </span>
          <span className="muted small">{s.count}</span>
        </button>
      ))}
      {value && (
        <button className="menu-item muted" onClick={() => onPick("")}>
          Tous les expéditeurs
        </button>
      )}
    </div>
  );
}
