import { ComingIn } from "@/components/ComingIn";
import { DashboardShell } from "@/components/DashboardShell";

export default function DashboardPage() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return (
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        <ComingIn release="D1">
          Set Clerk keys, then this page loads your account from GET /api/me. No model or
          provider details are shown.
        </ComingIn>
      </div>
    );
  }
  return <DashboardShell />;
}
