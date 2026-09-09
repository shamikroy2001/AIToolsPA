import { SignUp } from "@clerk/nextjs";
import { ComingIn } from "@/components/ComingIn";

export default function SignupPage() {
  const configured = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold tracking-tight">Create an account</h1>
      {configured ? (
        <SignUp routing="path" path="/signup" signInUrl="/login" />
      ) : (
        <ComingIn release="D1">
          Add Clerk keys to enable registration. After D1b, new accounts go through plan checkout.
        </ComingIn>
      )}
    </div>
  );
}
