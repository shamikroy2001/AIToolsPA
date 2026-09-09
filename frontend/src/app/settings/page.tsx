import { ComingIn } from "@/components/ComingIn";

export default function SettingsPage() {
  return (
    <div>
      <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
      <ComingIn release="D1">Account, notifications, working hours. No API keys.</ComingIn>
    </div>
  );
}
