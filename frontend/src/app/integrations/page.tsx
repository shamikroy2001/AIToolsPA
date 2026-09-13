import { ComingIn } from "@/components/ComingIn";
import { ConnectionsShell } from "@/components/ConnectionsShell";

export default function IntegrationsPage() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return (
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Connections</h1>
        <ComingIn release="D2">
          Gmail and Telegram. Connect returns 503 until OAuth is configured. Credentials stay on
          the server.
        </ComingIn>
      </div>
    );
  }
  return <ConnectionsShell />;
}
