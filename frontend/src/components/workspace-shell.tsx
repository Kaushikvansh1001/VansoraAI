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
  { href: "/usage", label: "AI providers" },
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
    <div className="min-h-screen md:grid md:grid-cols-[232px_1fr]">
      <aside className="border-b border-line bg-ivory p-4 md:border-r md:border-b-0">
        <Link href="/dashboard" className="mb-6 flex items-center gap-2">
          <Logo className="h-7 w-7" />
          <span className="font-semibold tracking-tight">VansoraAI</span>
        </Link>
        <nav className="flex flex-wrap gap-1 md:grid">
          {links.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-md px-3 py-2 text-sm ${active ? "bg-steel/10 font-medium text-steel" : "text-muted hover:text-ink"}`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div>
        <header className="flex items-center justify-between border-b border-line bg-ivory/80 px-6 py-3">
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
