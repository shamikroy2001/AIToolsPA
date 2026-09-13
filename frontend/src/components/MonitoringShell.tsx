"use client";

import { useAuth } from "@clerk/nextjs";
import { FormEvent, useEffect, useState } from "react";
import { apiUrl } from "@/lib/api";

type Monitor = {
  id: string;
  url: string;
  enabled: boolean;
  last_checked_at: string | null;
  last_changed_at: string | null;
  created_at: string;
};

type Schedule = {
  id: string;
  task_type: string;
  cadence: string;
  payload: Record<string, unknown>;
  enabled: boolean;
  next_run_at: string | null;
  created_at: string;
};

type Notice = {
  id: string;
  channel: string;
  title: string;
  body: string;
  created_at: string;
};

export function MonitoringShell() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [url, setUrl] = useState("https://");
  const [taskType, setTaskType] = useState("website_monitor");
  const [cadence, setCadence] = useState("daily");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function headers() {
    const token = await getToken();
    return { Authorization: `Bearer ${token ?? ""}`, "Content-Type": "application/json" };
  }

  async function load() {
    const auth = await headers();
    const [monitorRes, scheduleRes, noticeRes] = await Promise.all([
      fetch(apiUrl("/api/monitors"), { headers: auth }),
      fetch(apiUrl("/api/schedules"), { headers: auth }),
      fetch(apiUrl("/api/notifications"), { headers: auth }),
    ]);
    if (!monitorRes.ok || !scheduleRes.ok || !noticeRes.ok) {
      setError("Could not load monitoring data.");
      return;
    }
    setMonitors((await monitorRes.json()) as Monitor[]);
    setSchedules((await scheduleRes.json()) as Schedule[]);
    setNotices((await noticeRes.json()) as Notice[]);
  }

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    void load();
  }, [getToken, isLoaded, isSignedIn]);

  async function addMonitor(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/api/monitors"), {
        method: "POST",
        headers: await headers(),
        body: JSON.stringify({ url }),
      });
      if (!response.ok) {
        setError("Could not add that website. Use an http(s) URL.");
        return;
      }
      setUrl("https://");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function toggleMonitor(monitor: Monitor) {
    const response = await fetch(apiUrl(`/api/monitors/${monitor.id}`), {
      method: "PATCH",
      headers: await headers(),
      body: JSON.stringify({ enabled: !monitor.enabled }),
    });
    if (!response.ok) {
      setError("Could not update that website.");
      return;
    }
    await load();
  }

  async function removeMonitor(id: string) {
    const response = await fetch(apiUrl(`/api/monitors/${id}`), {
      method: "DELETE",
      headers: await headers(),
    });
    if (!response.ok) {
      setError("Could not remove that website.");
      return;
    }
    await load();
  }

  async function addSchedule(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/api/schedules"), {
        method: "POST",
        headers: await headers(),
        body: JSON.stringify({ task_type: taskType, cadence }),
      });
      if (!response.ok) {
        setError("Could not create that schedule.");
        return;
      }
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function toggleSchedule(schedule: Schedule) {
    const response = await fetch(apiUrl(`/api/schedules/${schedule.id}`), {
      method: "PATCH",
      headers: await headers(),
      body: JSON.stringify({ enabled: !schedule.enabled }),
    });
    if (!response.ok) {
      setError("Could not update that schedule.");
      return;
    }
    await load();
  }

  async function removeSchedule(id: string) {
    const response = await fetch(apiUrl(`/api/schedules/${id}`), {
      method: "DELETE",
      headers: await headers(),
    });
    if (!response.ok) {
      setError("Could not remove that schedule.");
      return;
    }
    await load();
  }

  if (!isLoaded) {
    return <p className="text-sm text-slate-600">Loading…</p>;
  }
  if (!isSignedIn) {
    return <p className="text-sm text-slate-600">Sign in to manage monitoring.</p>;
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Monitoring</h1>
        <p className="mt-2 text-slate-600">
          Watch websites and keep schedules. Change detection runs later; this page stores what to
          watch.
        </p>
      </div>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-medium">Websites</h2>
        <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={(event) => void addMonitor(event)}>
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com"
          />
          <button
            type="submit"
            className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
            disabled={busy}
          >
            Add
          </button>
        </form>
        <ul className="mt-4 space-y-3">
          {monitors.length === 0 ? (
            <li className="text-sm text-slate-600">No websites yet.</li>
          ) : (
            monitors.map((monitor) => (
              <li key={monitor.id} className="flex items-start justify-between gap-3 text-sm">
                <div>
                  <p className="font-medium break-all">{monitor.url}</p>
                  <p className="text-slate-500">
                    {monitor.enabled ? "Enabled" : "Paused"}
                    {monitor.last_changed_at
                      ? ` · changed ${new Date(monitor.last_changed_at).toLocaleString()}`
                      : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="rounded-md border border-slate-300 px-2 py-1"
                    onClick={() => void toggleMonitor(monitor)}
                  >
                    {monitor.enabled ? "Pause" : "Enable"}
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-slate-300 px-2 py-1"
                    onClick={() => void removeMonitor(monitor.id)}
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))
          )}
        </ul>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-medium">Schedules</h2>
        <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={(event) => void addSchedule(event)}>
          <select
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={taskType}
            onChange={(event) => setTaskType(event.target.value)}
          >
            <option value="website_monitor">Website monitor</option>
            <option value="assistant_ask">Assistant</option>
            <option value="gmail_analyze">Gmail analyze</option>
            <option value="telegram_notify">Telegram notify</option>
          </select>
          <select
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={cadence}
            onChange={(event) => setCadence(event.target.value)}
          >
            <option value="hourly">Hourly</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
          <button
            type="submit"
            className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60"
            disabled={busy}
          >
            Add
          </button>
        </form>
        <ul className="mt-4 space-y-3">
          {schedules.length === 0 ? (
            <li className="text-sm text-slate-600">No schedules yet.</li>
          ) : (
            schedules.map((schedule) => (
              <li key={schedule.id} className="flex items-start justify-between gap-3 text-sm">
                <div>
                  <p className="font-medium">
                    {schedule.task_type} · {schedule.cadence}
                  </p>
                  <p className="text-slate-500">
                    {schedule.enabled ? "Enabled" : "Paused"}
                    {schedule.next_run_at
                      ? ` · next ${new Date(schedule.next_run_at).toLocaleString()}`
                      : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="rounded-md border border-slate-300 px-2 py-1"
                    onClick={() => void toggleSchedule(schedule)}
                  >
                    {schedule.enabled ? "Pause" : "Enable"}
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-slate-300 px-2 py-1"
                    onClick={() => void removeSchedule(schedule.id)}
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))
          )}
        </ul>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="font-medium">Notifications</h2>
        <ul className="mt-3 space-y-3">
          {notices.length === 0 ? (
            <li className="text-sm text-slate-600">No notifications yet.</li>
          ) : (
            notices.map((notice) => (
              <li key={notice.id} className="text-sm">
                <p className="text-slate-500">
                  {new Date(notice.created_at).toLocaleString()} · {notice.channel}
                </p>
                <p className="font-medium">{notice.title}</p>
                {notice.body ? <p className="text-slate-700">{notice.body}</p> : null}
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}
