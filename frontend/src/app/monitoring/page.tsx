import { ComingIn } from "@/components/ComingIn";

export default function MonitoringPage() {
  return (
    <div>
      <h1 className="text-3xl font-semibold tracking-tight">Monitoring</h1>
      <ComingIn release="D2">
        Add websites, hash-check on a schedule, notify only when something meaningful changes.
      </ComingIn>
    </div>
  );
}
