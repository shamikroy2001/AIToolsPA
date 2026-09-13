import { ComingIn } from "@/components/ComingIn";
import { MonitoringShell } from "@/components/MonitoringShell";

export default function MonitoringPage() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return (
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Monitoring</h1>
        <ComingIn release="D2">
          Add websites and schedules. Hash-check polling is a later slice.
        </ComingIn>
      </div>
    );
  }
  return <MonitoringShell />;
}
