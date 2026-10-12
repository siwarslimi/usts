import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, MessagesSquare } from "lucide-react";
import { shortDate } from "./format";
import type { EmailItem, EmailPage } from "./types";
import { Avatar, CategoryBadge, Empty, PriorityMark, Spinner, StatusPill } from "./ui";

interface Props {
  data: EmailPage | null;
  loading: boolean;
  selectedId: number | null;
  onSelect: (e: EmailItem) => void;
  onPage: (p: number) => void;
}

export function EmailList({ data, loading, selectedId, onSelect, onPage }: Props) {
  if (!data)
    return (
      <div className="list-skeleton">
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className="sk-row" style={{ animationDelay: `${i * 60}ms` }}>
            <span className="sk sk-avatar" />
            <div>
              <span className="sk sk-line w60" />
              <span className="sk sk-line w90" />
              <span className="sk sk-line w40" />
            </div>
          </div>
        ))}
      </div>
    );

  const from = (data.page - 1) * data.page_size + 1;
  const to = Math.min(data.page * data.page_size, data.total);

  return (
    <>
      <ul className={`email-list scroll ${loading ? "is-loading" : ""}`}>
        {data.items.length === 0 && (
          <Empty icon={<Inbox size={22} />} title="Aucun e-mail">
            Aucun message ne correspond à ces filtres.
          </Empty>
        )}
        {data.items.map((e) => (
          <li key={e.id}>
            <button
              className={`email-row ${selectedId === e.id ? "selected" : ""} ${e.status === "to_process" ? "unread" : ""} ${
                e.status === "ignored" ? "dim" : ""
              }`}
              onClick={() => onSelect(e)}
            >
              <Avatar name={e.from_name} email={e.from_email} />
              <div className="row-main">
                <div className="row-top">
                  <span className="sender">{e.from_name || e.from_email}</span>
                  {e.thread_size > 1 && (
                    <span className="thread-count" title={`${e.thread_size} messages dans le fil`}>
                      <MessagesSquare size={12} />
                      {e.thread_size}
                    </span>
                  )}
                  <time className="row-date">{shortDate(e.received_at)}</time>
                </div>
                <div className="row-subject">{e.subject || "(sans objet)"}</div>
                <div className="row-snippet">{e.ai_summary || e.snippet}</div>
                <div className="row-meta">
                  <CategoryBadge category={e.category} pending={e.classification_status === "pending"} />
                  <PriorityMark priority={e.priority} />
                  {e.needs_review && (
                    <span className="review-flag" title="Classement IA à vérifier">
                      <AlertTriangle size={12} /> À vérifier
                    </span>
                  )}
                  {e.status !== "to_process" && <StatusPill status={e.status} />}
                </div>
              </div>
            </button>
          </li>
        ))}
      </ul>
      {data.total > 0 && (
        <div className="pager">
          <span>
            {from}–{to} sur {data.total}
          </span>
          {loading && <Spinner />}
          <div className="pager-btns">
            <button className="icon-btn" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)} aria-label="Page précédente">
              <ChevronLeft size={16} />
            </button>
            <span className="small muted">
              {data.page} / {data.pages}
            </span>
            <button className="icon-btn" disabled={data.page >= data.pages} onClick={() => onPage(data.page + 1)} aria-label="Page suivante">
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
