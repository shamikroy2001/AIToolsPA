"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { AskBox } from "@/components/AskBox";
import { apiUrl } from "@/lib/api";

type Task = {
  id: string;
  task_type: string;
  status: string;
  message: string | null;
  reply: string | null;
  credits_charged: number;
  created_at: string;
};

export function TasksShell() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const token = await getToken();
    const response = await fetch(apiUrl("/api/tasks"), {
      headers: { Authorization: `Bearer ${token ?? ""}` },
    });
    if (!response.ok) {
      setError("Could not load tasks.");
      return;
    }
    setTasks((await response.json()) as Task[]);
  }

  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return;
    }
    void load();
  }, [getToken, isLoaded, isSignedIn]);

  if (!isLoaded) {
    return <p className="text-sm text-slate-600">Loading…</p>;
  }
  if (!isSignedIn) {
    return <p className="text-sm text-slate-600">Sign in to view tasks.</p>;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">Tasks</h1>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <section className="rounded-lg border border-slate-200 bg-white p-5">
        <AskBox onComplete={() => void load()} />
      </section>
      <ul className="space-y-3">
        {tasks.map((task) => (
          <li key={task.id} className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
            <p className="text-slate-500">
              {new Date(task.created_at).toLocaleString()} · {task.status} · {task.credits_charged}{" "}
              credits
            </p>
            <p className="mt-2 font-medium">{task.message}</p>
            {task.reply ? <p className="mt-2 text-slate-700">{task.reply}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
