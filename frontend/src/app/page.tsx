import Link from "next/link";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold tracking-tight">A personal assistant that works for you</h1>
      <p className="max-w-2xl text-slate-600">
        Connect your inbox, watch the sites you care about, and get notified when something
        actually matters. You customize the assistant. We run the rest.
      </p>
      <div className="flex gap-3">
        <Link
          href="/signup"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white"
        >
          Get started
        </Link>
        <Link href="/pricing" className="rounded-md border border-slate-300 px-4 py-2 text-sm">
          View plans
        </Link>
      </div>
    </div>
  );
}
