export function ComingIn({ release, children }: { release: "D1" | "D2"; children: string }) {
  return (
    <p className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
      <span className="font-medium text-slate-800">{release}:</span> {children}
    </p>
  );
}
