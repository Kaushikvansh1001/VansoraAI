import { SiteHeader } from "@/components/site-header";

export function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-md px-6 py-12">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <div className="surface-card mt-6 rounded-lg border border-line p-5">{children}</div>
      </main>
    </div>
  );
}

export const fieldClass = "w-full rounded-md border border-line bg-surface px-3 py-2";
export const buttonClass = "rounded-md bg-ink px-4 py-2 text-sm text-pearl disabled:opacity-60";
