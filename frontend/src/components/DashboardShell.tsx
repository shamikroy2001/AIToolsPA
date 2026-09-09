"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { AskBox } from "@/components/AskBox";
import { apiUrl } from "@/lib/api";

type Me = {
  id: string;
  email: string;
  plan: string;
  status: string;
};

type Credits = {
  available: number;
  monthly_allowance: number;
  used_this_period: number;
  rollover: number;
  period_end: string | null;
};

export function DashboardShell() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [credits, setCredits] = useState<Credits | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) {
          setError("Missing session.");
          return;
        }
        const headers = { Authorization: `Bearer ${token}` };
        const [meRes, creditRes] = await Promise.all([
          fetch(apiUrl("/api/me"), { headers }),
          fetch(apiUrl("/api/credits"), { headers }),
        ]);
        if (!meRes.ok) {
          setError("Could not load your account.");
          return;
        }
        const meBody = (await meRes.json()) as Me;
        const creditBody = creditRes.ok ? ((await creditRes.json()) as Credits) : null;
        if (!cancelled) {
          setMe(meBody);
          setCredits(creditBody);
        }
      } catch {
        if (!cancelled) {
          setError("Could not reach the assistant service.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [getToken, isLoaded, isSignedIn]);

  if (!isLoaded) {
    return <p className="text-sm text-slate-600">Loading…</p>;
  }

  if (!isSignedIn) {
    return (
      <p className="text-sm text-slate-600">
        Sign in to open your dashboard. Clerk keys are required locally — see{" "}
        <code>.env.example</code>.
      </p>
    );
  }

  const renewal = credits?.period_end
    ? new Date(credits.period_end).toLocaleDateString()
    : "—";

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Welcome back</h1>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-medium">Your assistant</h2>
        <div className="mt-3">
          <AskBox />
        </div>
      </section>
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-medium">Usage</h2>
        {credits ? (
          <dl className="mt-3 grid gap-2 text-sm text-slate-700">
            <div>
              <dt className="text-slate-500">Assistant credits available</dt>
              <dd>{credits.available.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Used this period</dt>
              <dd>
                {credits.used_this_period.toLocaleString()} /{" "}
                {credits.monthly_allowance.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Rollover</dt>
              <dd>{credits.rollover.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Upcoming renewal</dt>
              <dd>{renewal}</dd>
            </div>
          </dl>
        ) : (
          <p className="mt-2 text-sm text-slate-600">Loading usage…</p>
        )}
      </section>
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-medium">Account</h2>
        {me ? (
          <p className="mt-2 text-sm text-slate-700">
            {me.email || "Signed in"} · {me.plan === "none" ? "No plan yet" : me.plan}
          </p>
        ) : (
          <p className="mt-2 text-sm text-slate-600">Loading your account…</p>
        )}
      </section>
    </div>
  );
}
