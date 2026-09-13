"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";

type Integration = {
  provider: string;
  name: string;
  description: string;
  status: string;
};

export function ConnectionsShell() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [items, setItems] = useState<Integration[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    const token = await getToken();
    const response = await fetch(apiUrl("/api/integrations"), {
      headers: { Authorization: `Bearer ${token ?? ""}` },
    });
    if (!response.ok) {
      setError("Could not load connections.");
      return;
    }
    setItems((await response.json()) as Integration[]);
  }

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    void load();
  }, [getToken, isLoaded, isSignedIn]);

  async function connect(provider: string) {
    setBusy(provider);
    setError(null);
    try {
      const token = await getToken();
      const response = await fetch(apiUrl(`/api/integrations/${provider}/connect`), {
        method: "POST",
        headers: { Authorization: `Bearer ${token ?? ""}` },
      });
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      if (!response.ok) {
        setError(
          body.detail ||
            "This connection is not ready yet. Credentials will stay on the server when it is.",
        );
        return;
      }
      await load();
    } finally {
      setBusy(null);
    }
  }

  if (!isLoaded) {
    return <p className="text-sm text-slate-600">Loading…</p>;
  }
  if (!isSignedIn) {
    return <p className="text-sm text-slate-600">Sign in to manage connections.</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Connections</h1>
        <p className="mt-2 text-slate-600">
          Gmail and Telegram stay on the server. Tokens are never shown in this page or the API.
        </p>
      </div>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <ul className="grid gap-4 sm:grid-cols-2">
        {items.map((item) => (
          <li key={item.provider} className="rounded-lg border border-slate-200 bg-white p-5">
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-medium">{item.name}</h2>
              <span className="text-xs uppercase tracking-wide text-slate-500">{item.status}</span>
            </div>
            <p className="mt-2 text-sm text-slate-600">{item.description}</p>
            <button
              type="button"
              className="mt-4 rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
              disabled={busy === item.provider || item.status === "connected"}
              onClick={() => void connect(item.provider)}
            >
              {busy === item.provider
                ? "Connecting…"
                : item.status === "connected"
                  ? "Connected"
                  : "Connect"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
