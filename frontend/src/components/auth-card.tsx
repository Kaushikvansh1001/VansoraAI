import { SiteHeader } from "@/components/site-header";

export function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas">
      <SiteHeader />
      <main className="mx-auto max-w-md px-6 py-12">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <div className="mt-6 rounded-lg border border-line bg-surface p-5">{children}</div>
      </main>
    </div>
  );
}

export const fieldClass = "w-full rounded-md border border-line bg-canvas px-3 py-2";
export const buttonClass = "rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-60";
