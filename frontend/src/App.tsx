import { useCallback, useEffect, useState } from "react";
import { api, setUnauthorizedHandler } from "./api";
import { EmailList } from "./EmailList";
import { FiltersBar } from "./FiltersBar";
import { useLiveUpdates } from "./live";
import { Login } from "./Login";
import { Sidebar, type View } from "./Sidebar";
import { ThreadPane } from "./ThreadPane";
import { TodayView } from "./TodayView";
import type { Counts, EmailItem, EmailPage, Filters, User } from "./types";
import { EMPTY_FILTERS } from "./types";
import { Spinner, useToast } from "./ui";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    api.me().then(setUser).catch(() => setUser(null));
  }, []);

  if (user === undefined)
    return (
      <div className="boot">
        <Spinner size={22} />
      </div>
    );
  if (user === null) return <Login onLogged={setUser} />;
  return (
    <Shell
      user={user}
      theme={theme}
      onTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      onLogout={async () => {
        await api.logout().catch(() => {});
        setUser(null);
      }}
    />
  );
}

function Shell({ user, theme, onTheme, onLogout }: { user: User; theme: Theme; onTheme: () => void; onLogout: () => void }) {
  const [view, setView] = useState<View>("today");
  const [filters, setFilters] = useState<Filters>({ ...EMPTY_FILTERS, status: ["to_process"] });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<EmailPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [selected, setSelected] = useState<EmailItem | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const { version, state } = useLiveUpdates(true);
  const toast = useToast();

  const loadList = useCallback(() => {
    setLoading(true);
    api
      .emails(filters, page)
      .then(setData)
      .catch((e) => toast.show({ kind: "err", text: e.message }))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, page]);

  useEffect(() => {
    if (view === "inbox") loadList();
  }, [view, loadList, version]);

  useEffect(() => {
    api.counts().then(setCounts).catch(() => {});
  }, [version, data]);

  const applyFilters = (f: Filters) => {
    setFilters(f);
    setPage(1);
    setView("inbox");
    setMenuOpen(false);
  };

  const openEmail = (e: EmailItem) => {
    setSelected(e);
    setView("inbox");
  };

  return (
    <div className="app">
      <Sidebar
        view={view}
        filters={filters}
        counts={counts}
        user={user}
        live={state}
        theme={theme}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        onToday={() => (setView("today"), setMenuOpen(false))}
        onFilters={applyFilters}
        onTheme={onTheme}
        onLogout={onLogout}
      />
      <main className="main">
        {view === "today" ? (
          <TodayView
            version={version}
            onOpen={openEmail}
            onMenu={() => setMenuOpen(true)}
            onShowAll={() => applyFilters({ ...EMPTY_FILTERS, status: ["to_process", "draft_ready"] })}
          />
        ) : (
          <div className={`inbox ${selected ? "has-selection" : ""}`}>
            <section className="list-col">
              <FiltersBar filters={filters} onChange={applyFilters} total={data?.total ?? null} onMenu={() => setMenuOpen(true)} />
              <EmailList data={data} loading={loading} selectedId={selected?.id ?? null} onSelect={setSelected} onPage={setPage} />
            </section>
            <section className="thread-col">
              <ThreadPane threadId={selected?.thread_id ?? null} version={version} onBack={() => setSelected(null)} notify={toast.show} />
            </section>
          </div>
        )}
      </main>
      {toast.node}
    </div>
  );
}
