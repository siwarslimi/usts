import { AlertTriangle, CheckCheck, EyeOff, FilePen, Inbox, LogOut, Mail, Moon, Sun, SunMedium, X } from "lucide-react";
import type { ReactNode } from "react";
import { CATEGORIES, CATEGORY_LABEL, catClass } from "./format";
import type { LiveState } from "./live";
import type { Category, Counts, Filters, Status, User } from "./types";
import { EMPTY_FILTERS } from "./types";

export type View = "today" | "inbox";

interface Props {
  view: View;
  filters: Filters;
  counts: Counts | null;
  user: User;
  live: LiveState;
  theme: "light" | "dark";
  open: boolean;
  onClose: () => void;
  onToday: () => void;
  onFilters: (f: Filters) => void;
  onTheme: () => void;
  onLogout: () => void;
}

const STATUS_ITEMS: { status: Status; label: string; icon: ReactNode }[] = [
  { status: "to_process", label: "À traiter", icon: <Inbox size={17} /> },
  { status: "draft_ready", label: "Brouillons prêts", icon: <FilePen size={17} /> },
  { status: "replied", label: "Répondus", icon: <CheckCheck size={17} /> },
  { status: "ignored", label: "Ignorés", icon: <EyeOff size={17} /> },
];

export function Sidebar(p: Props) {
  const f = p.filters;
  const inbox = p.view === "inbox";
  const onlyStatus = (s: Status) =>
    inbox && f.status.length === 1 && f.status[0] === s && !f.category.length && !f.needs_review;
  const onlyCategory = (c: Category) => inbox && f.category.length === 1 && f.category[0] === c && !f.status.length;
  const isAll = inbox && JSON.stringify(f) === JSON.stringify(EMPTY_FILTERS);
  const go = (patch: Partial<Filters>) => p.onFilters({ ...EMPTY_FILTERS, ...patch });

  return (
    <>
      <div className={`scrim ${p.open ? "show" : ""}`} onClick={p.onClose} />
      <aside className={`sidebar ${p.open ? "open" : ""}`}>
        <div className="sidebar-head">
          <div className="brand">
            <span className="brand-mark">
              <Mail size={15} strokeWidth={2.4} />
            </span>
            Courrier
          </div>
          <button className="icon-btn only-mobile" onClick={p.onClose} aria-label="Fermer le menu">
            <X size={18} />
          </button>
        </div>

        <nav className="nav">
          <NavItem active={p.view === "today"} icon={<SunMedium size={17} />} label="Aujourd'hui" onClick={p.onToday} />
          <NavItem active={isAll} icon={<Mail size={17} />} label="Tous les e-mails" count={p.counts?.total} onClick={() => go({})} />

          <div className="nav-section">Suivi</div>
          {STATUS_ITEMS.map((s) => (
            <NavItem
              key={s.status}
              active={onlyStatus(s.status)}
              icon={s.icon}
              label={s.label}
              count={p.counts?.status[s.status]}
              strong={s.status === "to_process"}
              onClick={() => go({ status: [s.status] })}
            />
          ))}
          <NavItem
            active={inbox && f.needs_review}
            icon={<AlertTriangle size={17} />}
            label="À vérifier"
            count={p.counts?.to_review}
            onClick={() => go({ needs_review: true })}
          />

          <div className="nav-section">Catégories ouvertes</div>
          {CATEGORIES.map((c) => (
            <NavItem
              key={c}
              active={onlyCategory(c)}
              icon={<span className={`cat-swatch ${catClass(c)}`} />}
              label={CATEGORY_LABEL[c]}
              count={p.counts?.category_open[c]}
              onClick={() => go({ category: [c] })}
            />
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className={`live live-${p.live}`} title="Mise à jour en temps réel (SSE)">
            <span className="live-dot" />
            {p.live === "live" ? "Temps réel actif" : p.live === "connecting" ? "Connexion…" : "Hors ligne"}
          </div>
          <div className="me">
            <span className="me-email" title={p.user.email}>
              {p.user.email}
            </span>
            <button className="icon-btn" onClick={p.onTheme} aria-label="Changer de thème" title="Thème clair / sombre">
              {p.theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button className="icon-btn" onClick={p.onLogout} aria-label="Se déconnecter" title="Se déconnecter">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}

function NavItem(props: { active: boolean; icon: ReactNode; label: string; count?: number; strong?: boolean; onClick: () => void }) {
  return (
    <button className={`nav-item ${props.active ? "active" : ""}`} onClick={props.onClick}>
      <span className="nav-icon">{props.icon}</span>
      <span className="nav-label">{props.label}</span>
      {!!props.count && <span className={`nav-count ${props.strong ? "strong" : ""}`}>{props.count}</span>}
    </button>
  );
}
