import { useState, type FormEvent } from "react";
import { ArrowRight, Lock, Mail } from "lucide-react";
import { api } from "./api";
import type { User } from "./types";
import { Spinner } from "./ui";

export function Login({ onLogged }: { onLogged: (u: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLogged(await api.login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connexion impossible");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-glow" aria-hidden />
      <form className="login-card" onSubmit={submit}>
        <div className="brand brand-lg">
          <span className="brand-mark">
            <Mail size={18} strokeWidth={2.2} />
          </span>
          Courrier
        </div>
        <h1>
          Votre boîte mail,
          <br />
          <em>enfin sereine.</em>
        </h1>
        <p className="muted">Tri par IA, priorités du jour et réponses rédigées pour vous, envoyées seulement quand vous le décidez.</p>

        <label className="field">
          <span>Adresse e-mail</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </label>
        <label className="field">
          <span>Mot de passe</span>
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <div className="form-error">{error}</div>}
        <button className="btn btn-primary btn-block" disabled={busy}>
          {busy ? <Spinner /> : <>Se connecter <ArrowRight size={16} /></>}
        </button>
        <p className="login-foot">
          <Lock size={12} /> Accès protégé : aucune donnée visible sans connexion
        </p>
      </form>
    </div>
  );
}
