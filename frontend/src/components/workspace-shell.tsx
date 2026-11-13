"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { useSession } from "@/lib/session";

const links = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/settings", label: "Organization" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/data-analyst", label: "Data analyst" },
  { href: "/workflows", label: "Workflows" },
  { href: "/support", label: "Support" },
  { href: "/usage", label: "Usage" },
];

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const { user, ready, logout } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (ready && !user) {
      router.replace("/login");
    }
  }, [ready, user, router]);

  if (!ready || !user) {
    return <p className="p-8 text-muted">Loading workspace…</p>;
  }

  return (
    <div className="min-h-screen bg-canvas md:grid md:grid-cols-[220px_1fr]">
      <aside className="bg-navy p-4 text-slate-100">
        <Link href="/dashboard" className="mb-6 flex items-center gap-2">
          <Logo className="h-7 w-7" />
          <span className="font-semibold">VansoraAI</span>
        </Link>
        <nav className="flex flex-wrap gap-2 md:grid">
          {links.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-md px-3 py-2 text-sm ${active ? "bg-white/10" : "text-slate-300"}`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div>
        <header className="flex items-center justify-between border-b border-line px-6 py-3">
          <p className="text-sm text-muted">{user.email}</p>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <button
              type="button"
              className="text-sm"
              onClick={async () => {
                await logout();
                router.replace("/");
              }}
            >
              Sign out
            </button>
          </div>
        </header>
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
