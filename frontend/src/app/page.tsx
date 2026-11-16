import Link from "next/link";
import { SiteHeader } from "@/components/site-header";

const today = [
  "Create an account and verify it",
  "Create an organization and invite members",
  "Open a dashboard whose counts come from the database",
  "Review AI provider health and real usage",
  "Draw a workflow and run it manually",
  "Review a support draft before it is kept",
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-6 pb-24 pt-16 md:pt-24">
        <p className="hero-kicker">Intelligence. Automation. Evolution.</p>
        <h1 className="mt-4 max-w-3xl text-4xl font-semibold tracking-tight md:text-5xl">
          A workspace for documents, data, and approved automation.
        </h1>
        <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-muted">
          VansoraAI is being built in phases. Accounts, organizations, and dashboard counts are stored in
          Supabase, so the same workspace opens on either computer. Provider health and a test prompt are
          available to organization admins. Knowledge, the data analyst, manual workflows, and support drafts are in the workspace.
        </p>
        <div className="mt-8 flex gap-2">
          <Link href="/register" className="btn-primary">
            Create account
          </Link>
          <Link href="/login" className="btn-secondary">
            Sign in
          </Link>
        </div>

        <section className="mt-20">
          <h2 className="text-sm font-medium text-muted">Working now</h2>
          <ul className="hero-grid mt-4">
            {today.map((item, index) => (
              <li key={item} className="surface-card hero-card rounded-lg border border-line">
                <p className="hero-index">0{index + 1}</p>
                <p className="mt-3 text-sm leading-relaxed">{item}</p>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
