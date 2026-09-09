import { ComingIn } from "@/components/ComingIn";
import { TasksShell } from "@/components/TasksShell";

export default function TasksPage() {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return (
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Tasks</h1>
        <ComingIn release="D1">Set Clerk keys to ask your assistant and list replies.</ComingIn>
      </div>
    );
  }
  return <TasksShell />;
}
