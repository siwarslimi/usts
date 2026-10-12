import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Menu, PartyPopper, Sparkles } from "lucide-react";
import { api } from "./api";
import { CATEGORIES, CATEGORY_LABEL, catClass, isoDate, relative, shiftDays } from "./format";
import type { EmailItem, Summary } from "./types";
import { Avatar, CategoryBadge, Empty, PriorityMark, Spinner } from "./ui";

interface Props {
  version: number;
  onOpen: (e: EmailItem) => void;
  onMenu: () => void;
  onShowAll: () => void;
}

export function TodayView({ version, onOpen, onMenu, onShowAll }: Props) {
  const [day, setDay] = useState(() => new Date());
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isToday = isoDate(day) === isoDate(new Date());

  useEffect(() => {
    let alive = true;
    api
      .summary(isoDate(day))
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [day, version]);

  const rawLabel = day.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  const dateLabel = rawLabel.charAt(0).toUpperCase() + rawLabel.slice(1);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Bonjour" : hour < 18 ? "Bon après-midi" : "Bonsoir";
  const open = data ? (data.by_status.to_process ?? 0) + (data.by_status.draft_ready ?? 0) : 0;
  const catTotal = data ? Object.values(data.by_category).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="today scroll">
      <header className="today-head">
        <button className="icon-btn only-mobile" onClick={onMenu} aria-label="Menu">
          <Menu size={20} />
        </button>
        <div>
          <p className="eyebrow">{isToday ? greeting : "Résumé du"}</p>
          <h1 className="display">{dateLabel}</h1>
        </div>
        <div className="day-nav">
          <button className="icon-btn" onClick={() => setDay((d) => shiftDays(d, -1))} aria-label="Jour précédent">
            <ChevronLeft size={18} />
          </button>
          <button className="btn btn-ghost btn-sm" disabled={isToday} onClick={() => setDay(new Date())}>
            Aujourd'hui
          </button>
          <button className="icon-btn" disabled={isToday} onClick={() => setDay((d) => shiftDays(d, 1))} aria-label="Jour suivant">
            <ChevronRight size={18} />
          </button>
        </div>
      </header>

      {error && <div className="form-error">{error}</div>}
      {!data && !error && (
        <div className="center-pad">
          <Spinner size={22} />
        </div>
      )}

      {data && (
        <>
          <section className="summary-card">
            <div className="summary-tag">
              <Sparkles size={14} />
              {data.text_source === "ai" ? "Résumé IA" : "Résumé automatique"}
            </div>
            <p className="summary-text">{data.text}</p>

            <div className="tiles">
              <Tile value={data.received} label="reçus" />
              <Tile value={open} label="en attente" accent />
              <Tile value={data.by_status.replied ?? 0} label="répondus" />
              <Tile value={data.to_review} label="à vérifier" warn={data.to_review > 0} />
            </div>

            {catTotal > 0 && (
              <div className="catbar-wrap">
                <div className="catbar" role="img" aria-label="Répartition par catégorie">
                  {CATEGORIES.filter((c) => data.by_category[c]).map((c) => (
                    <span key={c} className={catClass(c)} style={{ flexGrow: data.by_category[c] }} />
                  ))}
                </div>
                <ul className="legend">
                  {CATEGORIES.filter((c) => data.by_category[c]).map((c) => (
                    <li key={c}>
                      <span className={`cat-swatch ${catClass(c)}`} />
                      {CATEGORY_LABEL[c]} <b>{data.by_category[c]}</b>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section className="priorities">
            <div className="section-head">
              <h2>À traiter en priorité</h2>
              <button className="link" onClick={onShowAll}>
                Voir tout ce qui est à traiter →
              </button>
            </div>
            {data.top.length === 0 ? (
              <Empty icon={<PartyPopper size={22} />} title="Rien d'urgent">
                Aucun e-mail en attente de réponse. Profitez-en !
              </Empty>
            ) : (
              <ol className="prio-list">
                {data.top.map(({ email, reasons }, i) => (
                  <li key={email.id}>
                    <button className="prio-row" onClick={() => onOpen(email)}>
                      <span className="rank">{i + 1}</span>
                      <Avatar name={email.from_name} email={email.from_email} />
                      <div className="prio-main">
                        <div className="prio-top">
                          <strong>{email.from_name || email.from_email}</strong>
                          <span className="muted small">{relative(email.received_at)}</span>
                        </div>
                        <div className="prio-subject">{email.subject}</div>
                        {email.ai_summary && <div className="prio-summary">{email.ai_summary}</div>}
                        <div className="reasons">
                          {reasons.map((r) => (
                            <span key={r} className="reason">
                              {r}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="prio-side">
                        <CategoryBadge category={email.category} />
                        <PriorityMark priority={email.priority} withLabel />
                      </div>
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function Tile({ value, label, accent, warn }: { value: number; label: string; accent?: boolean; warn?: boolean }) {
  return (
    <div className={`tile ${accent ? "accent" : ""} ${warn ? "warn" : ""}`}>
      <span className="tile-value">{value}</span>
      <span className="tile-label">{label}</span>
    </div>
  );
}
