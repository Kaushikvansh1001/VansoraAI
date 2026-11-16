import { SiteHeader } from "@/components/site-header";

export function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-md px-6 py-12">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <div className="auth-card surface-card mt-6 rounded-lg border border-line p-5">{children}</div>
      </main>
    </div>
  );
}

export const fieldClass = "field w-full";
export const buttonClass = "btn-primary";
export const secondaryButtonClass = "btn-secondary px-4 py-2 text-sm";
