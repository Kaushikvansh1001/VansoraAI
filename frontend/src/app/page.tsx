import Link from "next/link";
import { SiteHeader } from "@/components/site-header";

const today = [
  "Create an account and verify it",
  "Create an organization and invite members",
  "Open a dashboard whose counts come from the database",
];

const later = [
  { title: "Knowledge assistant", text: "Upload documents, retrieve passages, and answer with citations." },
  { title: "Data analyst", text: "Ask questions about a spreadsheet through a validated analysis plan." },
  { title: "Workflows and support", text: "Draw an automation, require approval, and draft support replies." },
];

export default function HomePage() {
  return (
    <div className="min-h-screen bg-canvas">
      <SiteHeader />
      <main className="mx-auto max-w-5xl px-6 py-16">
        <p className="text-sm font-medium text-brand">Intelligence. Automation. Evolution.</p>
        <h1 className="mt-3 max-w-2xl text-4xl font-semibold tracking-tight">
          A workspace for documents, data, and approved automation.
        </h1>
        <p className="mt-4 max-w-2xl text-muted">
          VansoraAI is being built in phases. Accounts, organizations, and dashboard counts are stored in
          Supabase, so the same workspace opens on either computer. AI features are not wired up yet.
        </p>
        <div className="mt-8 flex gap-3">
          <Link href="/register" className="rounded-md bg-brand px-4 py-2 text-sm text-white">
            Create account
          </Link>
          <Link href="/login" className="rounded-md border border-line px-4 py-2 text-sm">
            Sign in
          </Link>
        </div>

        <section className="mt-16">
          <h2 className="text-lg font-semibold">Working now</h2>
          <ul className="mt-4 grid gap-3 md:grid-cols-3">
            {today.map((item) => (
              <li key={item} className="rounded-lg border border-line bg-surface p-4 text-sm">
                {item}
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-12">
          <h2 className="text-lg font-semibold">Later phases</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {later.map((item) => (
              <article key={item.title} className="rounded-lg border border-line bg-surface p-4">
                <h3 className="font-medium">{item.title}</h3>
                <p className="mt-2 text-sm text-muted">{item.text}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
