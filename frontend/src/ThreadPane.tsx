import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCheck,
  ChevronDown,
  EyeOff,
  Mail,
  RotateCcw,
  Send,
  Sparkles,
  Target,
  Undo2,
  X,
} from "lucide-react";
import { api, newIdempotencyKey } from "./api";
import { fullDate, relative } from "./format";
import type { Draft, EmailDetail, Thread, ThreadMessage, Tone } from "./types";
import { Avatar, CategoryBadge, Empty, Modal, PriorityMark, Spinner, StatusPill } from "./ui";

interface Props {
  threadId: number | null;
  version: number;
  onBack: () => void;
  notify: (t: { kind: "ok" | "err"; text: string }) => void;
}

const TONES: { id: Tone; label: string }[] = [
  { id: "formel", label: "Formel" },
  { id: "neutre", label: "Neutre" },
  { id: "court", label: "Court" },
];

export function ThreadPane({ threadId, version, onBack, notify }: Props) {
  const [thread, setThread] = useState<Thread | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (threadId == null) return;
    api
      .thread(threadId)
      .then((t) => (setThread(t), setError(null)))
      .catch((e) => setError(e.message));
  }, [threadId]);

  useEffect(() => {
    setThread(null);
    load();
  }, [load]);
  useEffect(() => {
    if (version) load();
  }, [version, load]);

  // Fallback polling while a reply is in flight (in case the live stream is down)
  const sending = thread?.replies.some((r) => r.status === "sending");
  useEffect(() => {
    if (!sending) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [sending, load]);

  if (threadId == null)
    return (
      <div className="thread thread-empty">
        <Empty icon={<Mail size={24} />} title="Sélectionnez un e-mail">
          Le fil de discussion complet s'affichera ici, avec la proposition de réponse.
        </Empty>
      </div>
    );

  if (error)
    return (
      <div className="thread">
        <div className="form-error">{error}</div>
      </div>
    );

  if (!thread)
    return (
      <div className="thread thread-empty">
        <Spinner size={22} />
      </div>
    );

  const latest = thread.emails[thread.emails.length - 1];

  async function setStatus(status: EmailDetail["status"]) {
    try {
      await api.setStatus(latest.id, status);
      notify({ kind: "ok", text: status === "ignored" ? "E-mail ignoré" : "Remis à traiter" });
      load();
    } catch (e) {
      notify({ kind: "err", text: (e as Error).message });
    }
  }

  return (
    <div className="thread scroll" key={thread.id}>
      <header className="thread-head">
        <button className="icon-btn only-narrow" onClick={onBack} aria-label="Retour à la liste">
          <ArrowLeft size={18} />
        </button>
        <div className="thread-title">
          <h2 className="display-sm">{thread.subject || "(sans objet)"}</h2>
          <div className="thread-sub">
            <StatusPill status={latest.status} />
            <span className="muted small">
              {thread.messages.length} message{thread.messages.length > 1 ? "s" : ""} · dernier {relative(thread.messages[thread.messages.length - 1].at)}
            </span>
          </div>
        </div>
        <div className="thread-actions">
          {latest.status === "ignored" ? (
            <button className="btn btn-ghost btn-sm" onClick={() => setStatus("to_process")}>
              <Undo2 size={15} /> Remettre à traiter
            </button>
          ) : latest.status !== "replied" ? (
            <button className="btn btn-ghost btn-sm" onClick={() => setStatus("ignored")}>
              <EyeOff size={15} /> Ignorer
            </button>
          ) : null}
        </div>
      </header>

      <AiCard email={latest} />

      <div className="messages">
        {thread.messages.map((m, i) => (
          <MessageCard
            key={`${m.kind}-${m.id}`}
            m={m}
            defaultOpen={i >= thread.messages.length - 2 || m.kind === "outgoing"}
            onRetry={
              m.kind === "outgoing" && m.status === "failed"
                ? async () => {
                    try {
                      await api.retry(m.id);
                      load();
                    } catch (e) {
                      notify({ kind: "err", text: (e as Error).message });
                    }
                  }
                : undefined
            }
          />
        ))}
      </div>

      {latest.status !== "ignored" && (
        <Composer
          key={latest.id}
          email={latest}
          initialDraft={thread.latest_draft}
          busy={!!sending}
          onSent={() => {
            notify({ kind: "ok", text: "Réponse validée, envoi en cours…" });
            load();
          }}
          notify={notify}
        />
      )}
    </div>
  );
}

function AiCard({ email }: { email: EmailDetail }) {
  return (
    <section className={`ai-card ${email.needs_review ? "review" : ""}`}>
      <div className="ai-card-head">
        <span className="ai-tag">
          <Sparkles size={13} /> Analyse IA
        </span>
        <CategoryBadge category={email.category} pending={email.classification_status === "pending"} />
        <PriorityMark priority={email.priority} withLabel />
      </div>
      {email.classification_status === "pending" ? (
        <p className="muted">Classement en attente : le workflow n8n de classification n'a pas encore traité ce message.</p>
      ) : (
        <>
          {email.ai_summary && <p className="ai-summary">{email.ai_summary}</p>}
          {email.expected_action && (
            <p className="ai-action">
              <Target size={14} /> {email.expected_action}
            </p>
          )}
        </>
      )}
      {email.needs_review && (
        <p className="review-note">
          <AlertTriangle size={14} /> La sortie de l'IA était invalide deux fois : classé « Autre » par défaut, à vérifier.
        </p>
      )}
    </section>
  );
}

function MessageCard({ m, defaultOpen, onRetry }: { m: ThreadMessage; defaultOpen: boolean; onRetry?: () => void }) {
  const [open, setOpen] = useState(defaultOpen);
  const out = m.kind === "outgoing";
  return (
    <article className={`msg ${out ? "msg-out" : ""} ${open ? "open" : ""}`}>
      <button className="msg-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {out ? (
          <span className="avatar avatar-me" style={{ width: 32, height: 32, fontSize: 12 }}>
            Moi
          </span>
        ) : (
          <Avatar name={m.from_name} email={m.from_email} size={32} />
        )}
        <div className="msg-who">
          <strong>{out ? "Vous" : m.from_name || m.from_email}</strong>
          <span className="muted small">{out ? `à ${m.to.join(", ")}` : m.from_email}</span>
        </div>
        <time className="muted small" title={fullDate(m.at)}>
          {fullDate(m.at)}
        </time>
        {!open && <ChevronDown size={16} className="muted" />}
      </button>
      {open ? <div className="msg-body">{m.body_text}</div> : <div className="msg-preview">{m.body_text.slice(0, 140)}</div>}
      {out && <SendState status={m.status} error={m.error} onRetry={onRetry} />}
    </article>
  );
}

function SendState({ status, error, onRetry }: { status: ThreadMessage["status"]; error: string | null; onRetry?: () => void }) {
  if (status === "sending")
    return (
      <div className="send-state sending">
        <Spinner size={13} /> Envoi en cours…
      </div>
    );
  if (status === "sent")
    return (
      <div className="send-state sent">
        <CheckCheck size={15} /> Envoyé dans le fil de discussion
      </div>
    );
  return (
    <div className="send-state failed">
      <X size={15} /> Échec de l'envoi{error ? ` : ${error}` : ""}
      {onRetry && (
        <button className="btn btn-sm btn-danger-soft" onClick={onRetry}>
          <RotateCcw size={14} /> Réessayer
        </button>
      )}
    </div>
  );
}

function Composer({
  email,
  initialDraft,
  busy,
  onSent,
  notify,
}: {
  email: EmailDetail;
  initialDraft: Draft | null;
  busy: boolean;
  onSent: () => void;
  notify: Props["notify"];
}) {
  const alreadyReplied = email.status === "replied";
  const [body, setBody] = useState(alreadyReplied ? "" : initialDraft?.body ?? "");
  const [draft, setDraft] = useState<Draft | null>(alreadyReplied ? null : initialDraft);
  const [tone, setTone] = useState<Tone>(initialDraft?.tone ?? "neutre");
  const [generating, setGenerating] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  const [expanded, setExpanded] = useState(!!initialDraft && !alreadyReplied);
  // One key per composed reply: double clicks and retries of the same request reuse it
  const keyRef = useRef(newIdempotencyKey());
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight + 2, 480)}px`;
  }, [body, expanded]);

  async function generate() {
    setGenerating(true);
    setExpanded(true);
    try {
      const d = await api.draft(email.id, tone);
      setDraft(d);
      setBody(d.body);
    } catch (e) {
      notify({ kind: "err", text: (e as Error).message });
    } finally {
      setGenerating(false);
    }
  }

  async function send() {
    setSending(true);
    try {
      await api.reply(email.id, body.trim(), keyRef.current, draft?.id);
      keyRef.current = newIdempotencyKey();
      setBody("");
      setDraft(null);
      setConfirming(false);
      setExpanded(false);
      onSent();
    } catch (e) {
      // Keep the same key: if the request actually reached the server, resending is a no-op
      notify({ kind: "err", text: (e as Error).message });
    } finally {
      setSending(false);
    }
  }

  if (!expanded)
    return (
      <div className="composer composer-collapsed">
        <button className="btn btn-ghost" onClick={() => (setExpanded(true), setTimeout(() => area.current?.focus(), 30))}>
          Répondre{alreadyReplied ? " à nouveau" : ""}
        </button>
        <div className="tone-wrap">
          <ToneSwitch tone={tone} onTone={setTone} />
          <button className="btn btn-ai" onClick={generate} disabled={generating}>
            {generating ? <Spinner /> : <Sparkles size={15} />} Proposer une réponse
          </button>
        </div>
      </div>
    );

  return (
    <section className="composer">
      <div className="composer-head">
        <span className="small muted">
          Réponse à <b>{email.from_name || email.from_email}</b> &lt;{email.from_email}&gt;
        </span>
        <button className="icon-btn icon-btn-sm" onClick={() => setExpanded(false)} aria-label="Réduire">
          <X size={14} />
        </button>
      </div>

      <div className="composer-tools">
        <ToneSwitch tone={tone} onTone={setTone} />
        <button className="btn btn-ai btn-sm" onClick={generate} disabled={generating}>
          {generating ? <Spinner /> : <Sparkles size={14} />}
          {draft ? "Régénérer" : "Rédiger avec l'IA"}
        </button>
      </div>

      {draft && (
        <div className={`draft-note ${draft.source}`}>
          <Sparkles size={13} />
          {draft.source === "ai"
            ? `Brouillon IA (ton ${draft.tone}) : relisez et modifiez-le librement. Rien ne part sans votre validation.`
            : `Modèle automatique (ton ${draft.tone}), aucune clé IA configurée. Modifiez-le avant d'envoyer.`}
        </div>
      )}

      <div className={`editor ${generating ? "generating" : ""}`}>
        <textarea
          ref={area}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Écrivez votre réponse…"
          rows={6}
          disabled={generating}
        />
        {generating && (
          <div className="editor-overlay">
            <Spinner /> Rédaction en cours…
          </div>
        )}
      </div>

      <div className="composer-foot">
        <span className="small muted">{body.trim() ? `${body.trim().split(/\s+/).length} mots` : ""}</span>
        <button className="btn btn-primary" disabled={!body.trim() || generating || busy} onClick={() => setConfirming(true)}>
          <Send size={15} /> Envoyer…
        </button>
      </div>

      {confirming && (
        <Modal title="Confirmer l'envoi" onClose={() => !sending && setConfirming(false)}>
          <p className="muted">
            Cette réponse sera envoyée à <b>{email.from_email}</b>, dans le même fil de discussion.
          </p>
          <blockquote className="confirm-preview">{body.trim()}</blockquote>
          <div className="modal-actions">
            <button className="btn btn-ghost" onClick={() => setConfirming(false)} disabled={sending}>
              Annuler
            </button>
            <button className="btn btn-primary" onClick={send} disabled={sending}>
              {sending ? <Spinner /> : <Check size={15} />} Valider et envoyer
            </button>
          </div>
        </Modal>
      )}
    </section>
  );
}

function ToneSwitch({ tone, onTone }: { tone: Tone; onTone: (t: Tone) => void }) {
  return (
    <div className="segmented" role="radiogroup" aria-label="Ton de la réponse">
      {TONES.map((t) => (
        <button key={t.id} role="radio" aria-checked={tone === t.id} className={tone === t.id ? "on" : ""} onClick={() => onTone(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
