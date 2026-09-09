import { ComingIn } from "@/components/ComingIn";
import { AssistantShell } from "@/components/AssistantShell";

export default function AssistantPage() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return (
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Assistant</h1>
        <p className="mt-2 text-slate-600">
          Name, personality, response style, timezone, language — never model or provider settings.
        </p>
        <ComingIn release="D1">Set Clerk keys to edit your assistant profile.</ComingIn>
      </div>
    );
  }
  return <AssistantShell />;
}
