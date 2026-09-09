"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";

type Profile = {
  assistant_name: string;
  personality: string;
  response_style: string;
  timezone: string;
  language: string;
};

export function AssistantShell() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    let cancelled = false;
    (async () => {
      const token = await getToken();
      const response = await fetch(apiUrl("/api/me/assistant"), {
        headers: { Authorization: `Bearer ${token ?? ""}` },
      });
      if (!response.ok) {
        if (!cancelled) {
          setError("Could not load your assistant.");
        }
        return;
      }
      const body = (await response.json()) as Profile;
      if (!cancelled) {
        setProfile(body);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [getToken, isLoaded, isSignedIn]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!profile) {
      return;
    }
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const token = await getToken();
      const response = await fetch(apiUrl("/api/me/assistant"), {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token ?? ""}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(profile),
      });
      if (!response.ok) {
        setError("Could not save your assistant.");
        return;
      }
      setProfile((await response.json()) as Profile);
      setSaved(true);
    } finally {
      setBusy(false);
    }
  }

  if (!isLoaded) {
    return <p className="text-sm text-slate-600">Loading…</p>;
  }
  if (!isSignedIn) {
    return <p className="text-sm text-slate-600">Sign in to customize your assistant.</p>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Assistant</h1>
      <p className="text-slate-600">
        Name, personality, response style, timezone, and language. These shape how your assistant
        replies — not how it is routed internally.
      </p>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {saved ? <p className="text-sm text-emerald-700">Saved.</p> : null}
      {profile ? (
        <form className="max-w-lg space-y-3" onSubmit={(event) => void save(event)}>
          {(
            [
              ["assistant_name", "Name"],
              ["personality", "Personality"],
              ["response_style", "Response style"],
              ["timezone", "Timezone"],
              ["language", "Language"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="block text-sm">
              <span className="text-slate-600">{label}</span>
              <input
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2"
                value={profile[key]}
                onChange={(event) => setProfile({ ...profile, [key]: event.target.value })}
              />
            </label>
          ))}
          <button
            type="submit"
            className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white"
            disabled={busy}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </form>
      ) : (
        <p className="text-sm text-slate-600">Loading your assistant…</p>
      )}
    </div>
  );
}
