import { ComingIn } from "@/components/ComingIn";
import { BillingShell } from "@/components/BillingShell";

export default function BillingPage() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return (
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Billing</h1>
        <ComingIn release="D1">
          Sign in with Clerk to see your plan and credits. Stripe checkout is disconnected until
          billing is re-enabled.
        </ComingIn>
        <ComingIn release="D2">Buy additional credits (top-up packs).</ComingIn>
      </div>
    );
  }
  return <BillingShell />;
}
