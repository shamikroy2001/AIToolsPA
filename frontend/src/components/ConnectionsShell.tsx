"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";

type Integration = {
  provider: string;
  name: string;
  description: string;
  status: string;
  account_label?: string | null;
  authorize_url?: string | null;
};

export function ConnectionsShell() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [items, setItems] = useState<Integration[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [chatId, setChatId] = useState("");

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
    const params = new URLSearchParams(window.location.search);
    const gmail = params.get("gmail");
    if (gmail === "connected") {
      setNotice("Gmail is connected. Tokens stay on the server.");
    } else if (gmail === "error") {
      setError("Gmail connection did not finish. You can try again.");
    }
    if (gmail) {
      window.history.replaceState({}, "", "/integrations");
    }
  }, []);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    void load();
  }, [getToken, isLoaded, isSignedIn]);

  async function connect(provider: string) {
    setBusy(provider);
    setError(null);
    setNotice(null);
    try {
      const token = await getToken();
      const payload =
        provider === "telegram" ? { chat_id: chatId.trim() } : undefined;
      const response = await fetch(apiUrl(`/api/integrations/${provider}/connect`), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token ?? ""}`,
          ...(payload ? { "Content-Type": "application/json" } : {}),
        },
        body: payload ? JSON.stringify(payload) : undefined,
      });
      const body = (await response.json().catch(() => ({}))) as Integration & {
        detail?: string;
      };
      if (!response.ok) {
        setError(
          body.detail ||
            "This connection is not ready yet. Credentials will stay on the server when it is.",
        );
        return;
      }
      if (body.authorize_url) {
        window.location.assign(body.authorize_url);
        return;
      }
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function disconnect(provider: string) {
    setBusy(provider);
    setError(null);
    setNotice(null);
    try {
      const token = await getToken();
      const response = await fetch(apiUrl(`/api/integrations/${provider}/disconnect`), {
        method: "POST",
        headers: { Authorization: `Bearer ${token ?? ""}` },
      });
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      if (!response.ok) {
        setError(body.detail || "Could not disconnect.");
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
      {notice ? <p className="text-sm text-emerald-700">{notice}</p> : null}
      <ul className="grid gap-4 sm:grid-cols-2">
        {items.map((item) => (
          <li key={item.provider} className="rounded-lg border border-slate-200 bg-white p-5">
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-medium">{item.name}</h2>
              <span className="text-xs uppercase tracking-wide text-slate-500">{item.status}</span>
            </div>
            {item.account_label ? (
              <p className="mt-1 text-sm text-slate-700">{item.account_label}</p>
            ) : null}
            <p className="mt-2 text-sm text-slate-600">{item.description}</p>
            {item.provider === "telegram" && item.status !== "connected" ? (
              <label className="mt-4 block text-sm text-slate-700">
                Chat ID
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  value={chatId}
                  onChange={(event) => setChatId(event.target.value)}
                  placeholder="Numeric chat ID from Telegram"
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
            ) : null}
            {item.status === "connected" ? (
              <button
                type="button"
                className="mt-4 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 disabled:opacity-60"
                disabled={busy === item.provider}
                onClick={() => void disconnect(item.provider)}
              >
                {busy === item.provider ? "Disconnecting…" : "Disconnect"}
              </button>
            ) : (
              <button
                type="button"
                className="mt-4 rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
                disabled={
                  busy === item.provider ||
                  (item.provider === "telegram" && !chatId.trim())
                }
                onClick={() => void connect(item.provider)}
              >
                {busy === item.provider ? "Connecting…" : "Connect"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
