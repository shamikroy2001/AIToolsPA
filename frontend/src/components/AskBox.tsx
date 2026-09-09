"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useState } from "react";
import { apiUrl } from "@/lib/api";

type Task = {
  id: string;
  status: string;
  reply: string | null;
  credits_charged: number;
};

export function AskBox({ onComplete }: { onComplete?: () => void }) {
  const { getToken } = useAuth();
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [upgrade, setUpgrade] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    setUpgrade(false);
    setReply(null);
    try {
      const token = await getToken();
      const response = await fetch(apiUrl("/api/tasks"), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token ?? ""}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
      });
      const body = (await response.json()) as Task & { detail?: string };
      if (response.status === 402) {
        setUpgrade(true);
        setError(typeof body.detail === "string" ? body.detail : "You've used your assistant credits.");
        return;
      }
      if (!response.ok) {
        setError("Your assistant could not complete that request. Try again shortly.");
        return;
      }
      setReply(body.reply);
      setMessage("");
      onComplete?.();
    } catch {
      setError("Could not reach the assistant service.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <label className="block text-sm font-medium text-slate-700" htmlFor="ask-message">
        Ask your assistant
      </label>
      <textarea
        id="ask-message"
        className="w-full rounded-md border border-slate-300 p-3 text-sm"
        rows={4}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder="What should I help with?"
        required
      />
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {upgrade ? (
        <p className="text-sm">
          <Link href="/billing" className="underline">
            Upgrade your plan
          </Link>{" "}
          to continue.
        </p>
      ) : null}
      {reply ? <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-800">{reply}</p> : null}
      <button
        type="submit"
        className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-50"
        disabled={busy || !message.trim()}
      >
        {busy ? "Working…" : "Send"}
      </button>
    </form>
  );
}
