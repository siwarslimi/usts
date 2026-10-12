import { useEffect, useRef, useState, type ReactNode } from "react";
import { CATEGORY_LABEL, PRIORITY_LABEL, STATUS_LABEL, catClass, hue, initials } from "./format";
import type { Category, Status } from "./types";

export function Avatar({ name, email, size = 36 }: { name: string; email: string; size?: number }) {
  const h = hue(email || name);
  return (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.38, ["--h" as string]: h }}
      aria-hidden
    >
      {initials(name, email)}
    </span>
  );
}

export function CategoryBadge({ category, pending }: { category: Category | null; pending?: boolean }) {
  if (!category)
    return <span className="badge cat-none">{pending ? "Classement…" : "Non classé"}</span>;
  return (
    <span className={`badge ${catClass(category)}`}>
      <span className="dot" />
      {CATEGORY_LABEL[category]}
    </span>
  );
}

export function PriorityMark({ priority, withLabel }: { priority: number | null; withLabel?: boolean }) {
  if (!priority) return null;
  return (
    <span className={`prio prio-${priority}`} title={`Priorité ${PRIORITY_LABEL[priority].toLowerCase()}`}>
      <span className="bars" aria-hidden>
        <i />
        <i />
        <i />
      </span>
      {withLabel && <span>{PRIORITY_LABEL[priority]}</span>}
    </span>
  );
}

export function StatusPill({ status }: { status: Status }) {
  return <span className={`status status-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function Spinner({ size = 14 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-label="Chargement" />;
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}

/** Small popover anchored to a trigger button; closes on outside click and Escape. */
export function Popover({
  trigger,
  children,
  align = "left",
}: {
  trigger: (open: boolean, toggle: () => void) => ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div className="popover-wrap" ref={ref}>
      {trigger(open, () => setOpen((o) => !o))}
      {open && <div className={`popover popover-${align}`}>{children(() => setOpen(false))}</div>}
    </div>
  );
}

export function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" role="dialog" aria-modal aria-label={title} onMouseDown={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  );
}

export function useToast() {
  const [toast, setToast] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3800);
    return () => clearTimeout(t);
  }, [toast]);
  const node = toast ? (
    <div className={`toast toast-${toast.kind}`} role="status">
      {toast.text}
    </div>
  ) : null;
  return { show: setToast, node };
}
