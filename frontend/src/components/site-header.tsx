"use client";

import Link from "next/link";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { useSession } from "@/lib/session";

export function SiteHeader() {
  const { user } = useSession();

  return (
    <header className="flex items-center justify-between border-b border-line bg-ivory/75 px-6 py-4">
      <Link href="/" className="flex items-center gap-3">
        <Logo />
        <span className="text-lg font-semibold">VansoraAI</span>
      </Link>
      <div className="flex items-center gap-3">
        <ThemeToggle />
        {user ? (
          <Link href="/dashboard" className="rounded-md bg-ink px-3 py-1.5 text-sm text-pearl">
            Workspace
          </Link>
        ) : (
          <>
            <Link href="/login" className="text-sm">
              Sign in
            </Link>
            <Link href="/register" className="rounded-md bg-ink px-3 py-1.5 text-sm text-pearl">
              Create account
            </Link>
          </>
        )}
      </div>
    </header>
  );
}
