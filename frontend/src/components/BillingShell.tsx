"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { ComingIn } from "@/components/ComingIn";
import { apiUrl } from "@/lib/api";

type Billing = {
  plan: string;
  plan_display_name: string | null;
  status: string;
  amount_cents: number | null;
  currency: string | null;
  monthly_credits: number;
  rollover_cap: number;
  stripe_enabled: boolean;
  credits: {
    available: number;
    used_this_period: number;
    rollover: number;
  };
};

function formatMoney(cents: number | null, currency: string | null): string {
  if (cents == null) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: (currency || "usd").toUpperCase(),
  }).format(cents / 100);
}

export function BillingShell() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [billing, setBilling] = useState<Billing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    let cancelled = false;
    (async () => {
      const token = await getToken();
      if (!token) {
        return;
      }
      const response = await fetch(apiUrl("/api/billing"), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        if (!cancelled) {
          setError("Could not load billing.");
        }
        return;
      }
      const body = (await response.json()) as Billing;
      if (!cancelled) {
        setBilling(body);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [getToken, isLoaded, isSignedIn]);

  async function startCheckout(plan: string) {
    setBusy(plan);
    setError(null);
    try {
      const token = await getToken();
      const response = await fetch(apiUrl("/api/billing/checkout"), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token ?? ""}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ plan }),
      });
      const body = await response.json();
      if (!response.ok || !body.url) {
        setError("Checkout is not available yet.");
        return;
      }
      window.location.href = body.url;
    } finally {
      setBusy(null);
    }
  }

  async function openPortal() {
    setBusy("portal");
    setError(null);
    try {
      const token = await getToken();
      const response = await fetch(apiUrl("/api/billing/portal"), {
        method: "POST",
        headers: { Authorization: `Bearer ${token ?? ""}` },
      });
      const body = await response.json();
      if (!response.ok || !body.url) {
        setError("Open Manage billing after your first subscription.");
        return;
      }
      window.location.href = body.url;
    } finally {
      setBusy(null);
    }
  }

  if (!isLoaded) {
    return <p className="text-sm text-slate-600">Loading…</p>;
  }
  if (!isSignedIn) {
    return <p className="text-sm text-slate-600">Sign in to manage billing.</p>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Billing</h1>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {billing ? (
        <section className="rounded-lg border border-slate-200 bg-white p-5 text-sm">
          <p>
            <span className="text-slate-500">Current plan</span>
            <br />
            <span className="text-lg font-medium">
              {billing.plan_display_name || billing.plan}
            </span>
          </p>
          <p className="mt-3">{formatMoney(billing.amount_cents, billing.currency)} / month</p>
          <p className="mt-3">Monthly credits {billing.monthly_credits.toLocaleString()}</p>
          <p>Rollover allowance {billing.rollover_cap.toLocaleString()}</p>
          <p>Current usage {billing.credits.used_this_period.toLocaleString()}</p>
          <p>Available {billing.credits.available.toLocaleString()}</p>
          <p className="mt-2 text-slate-500">Status: {billing.status}</p>
        </section>
      ) : (
        <p className="text-sm text-slate-600">Loading plan…</p>
      )}
      {billing && !billing.stripe_enabled ? (
        <p className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
          Paid checkout is paused. Stripe is disconnected for this environment. Plan amounts and
          credit balances still show; subscriptions are not charged.
        </p>
      ) : null}
      {billing && billing.stripe_enabled ? (
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white"
          onClick={() => startCheckout("pro")}
          disabled={busy !== null}
        >
          {busy === "pro" ? "Redirecting…" : "Upgrade to Pro"}
        </button>
        <button
          type="button"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          onClick={() => startCheckout("premium")}
          disabled={busy !== null}
        >
          Premium
        </button>
        <button
          type="button"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          onClick={() => void openPortal()}
          disabled={busy !== null}
        >
          Manage billing
        </button>
      </div>
      ) : null}
      <ComingIn release="D2">Buy additional credits (top-up packs).</ComingIn>
    </div>
  );
}
