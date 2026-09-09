"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";

type Plan = {
  slug: string;
  display_name: string;
  monthly_credits: number;
  rollover_cap: number;
  amount_cents: number;
  currency: string;
};

function formatMoney(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

export default function PricingPage() {
  const [plans, setPlans] = useState<Plan[]>([]);

  useEffect(() => {
    fetch(apiUrl("/api/plans"))
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setPlans(Array.isArray(data) ? data : []))
      .catch(() => setPlans([]));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Pricing</h1>
      <p className="text-slate-600">
        Subscribe to assistant capability. Amounts come from the service configuration, not from
        hard-coded prices in this page.
      </p>
      <div className="grid gap-4 md:grid-cols-3">
        {plans.map((plan) => (
          <article key={plan.slug} className="rounded-lg border border-slate-200 bg-white p-5">
            <h2 className="text-lg font-medium">{plan.display_name}</h2>
            <p className="mt-1 text-2xl font-semibold">
              {formatMoney(plan.amount_cents, plan.currency)}
              <span className="text-sm font-normal text-slate-500">/mo</span>
            </p>
            <p className="mt-3 text-sm text-slate-600">
              {plan.monthly_credits.toLocaleString()} credits / month
            </p>
            <p className="text-sm text-slate-600">
              Rollover cap {plan.rollover_cap.toLocaleString()}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
}
