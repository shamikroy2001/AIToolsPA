import { SignIn } from "@clerk/nextjs";
import { ComingIn } from "@/components/ComingIn";

export default function LoginPage() {
  const configured = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">Log in</h1>
      {configured ? (
        <SignIn routing="path" path="/login" signUpUrl="/signup" />
      ) : (
        <ComingIn release="D1">
          Add NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY to enable Clerk sign-in.
        </ComingIn>
      )}
    </div>
  );
}
