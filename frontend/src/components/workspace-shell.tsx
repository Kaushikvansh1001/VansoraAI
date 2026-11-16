"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { useSession } from "@/lib/session";

const links = [
  { href: "/dashboard", label: "Dashboard", icon: "grid" },
  { href: "/settings", label: "Organization", icon: "org" },
  { href: "/knowledge", label: "Knowledge", icon: "book" },
  { href: "/data-analyst", label: "Data analyst", icon: "chart" },
  { href: "/workflows", label: "Workflows", icon: "flow" },
  { href: "/support", label: "Support", icon: "chat" },
  { href: "/usage", label: "AI providers", icon: "spark" },
];

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const { user, ready, logout, organizations, organization, organizationId, selectOrganization } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (ready && !user) {
      router.replace("/login");
    }
  }, [ready, user, router]);

  if (!ready || !user) {
    return (
      <p className="workspace-loading">
        <span className="spinner" aria-hidden="true" />
        Loading workspace…
      </p>
    );
  }

  return (
    <div className="workspace-frame">
      <aside className="workspace-nav">
        <Link href="/dashboard" className="workspace-brand">
          <Logo className="h-7 w-7" />
          <span>VansoraAI</span>
        </Link>
        {organizations.length > 1 ? (
          <label className="org-switch">
            <span>Organization</span>
            <select
              className="field"
              value={organizationId ?? ""}
              onChange={(event) => selectOrganization(event.target.value)}
            >
              {organizations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        ) : organization ? (
          <p className="org-static">
            Organization
            <strong>{organization.name}</strong>
          </p>
        ) : null}
        <nav>
          {links.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link key={link.href} href={link.href} className="nav-link" data-active={active ? "true" : "false"}>
                <NavIcon name={link.icon} />
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="nav-foot">
          <p className="nav-user" title={user.email}>
            {user.email}
          </p>
          <div className="nav-foot-actions">
            <ThemeToggle />
            <button
              type="button"
              className="btn-secondary"
              onClick={async () => {
                await logout();
                router.replace("/");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>
      <div className="min-w-0">
        <main className="workspace-main">{children}</main>
      </div>
    </div>
  );
}

function NavIcon({ name }: { name: string }) {
  const props = {
    width: 16,
    height: 16,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (name === "grid") {
    return (
      <svg {...props}>
        <rect x="2" y="2" width="5" height="5" rx="1" />
        <rect x="9" y="2" width="5" height="5" rx="1" />
        <rect x="2" y="9" width="5" height="5" rx="1" />
        <rect x="9" y="9" width="5" height="5" rx="1" />
      </svg>
    );
  }
  if (name === "org") {
    return (
      <svg {...props}>
        <path d="M3 13.5V4.5L8 2.5l5 2v9" />
        <path d="M6.5 13.5v-3h3v3" />
      </svg>
    );
  }
  if (name === "book") {
    return (
      <svg {...props}>
        <path d="M3 3.5h4.2A2.3 2.3 0 0 1 9.5 5.8V13a2 2 0 0 0-2.3-1.2H3z" />
        <path d="M13 3.5H8.8A2.3 2.3 0 0 0 6.5 5.8V13a2 2 0 0 1 2.3-1.2H13z" />
      </svg>
    );
  }
  if (name === "chart") {
    return (
      <svg {...props}>
        <path d="M2.5 12.5h11" />
        <path d="M4.5 12.5v-3" />
        <path d="M8 12.5V6" />
        <path d="M11.5 12.5V3.5" />
      </svg>
    );
  }
  if (name === "flow") {
    return (
      <svg {...props}>
        <circle cx="4" cy="4" r="1.4" />
        <circle cx="12" cy="8" r="1.4" />
        <circle cx="4" cy="12" r="1.4" />
        <path d="M5.4 4h3.2a2 2 0 0 1 2 2v.6" />
        <path d="M5.4 12h3.2a2 2 0 0 0 2-2v-.6" />
      </svg>
    );
  }
  if (name === "chat") {
    return (
      <svg {...props}>
        <path d="M3 4.5h10v6.2H6.2L3 13z" />
      </svg>
    );
  }
  return (
    <svg {...props}>
      <path d="M8 2.2l1.1 3.2H12.5L10 7.4l.9 3.2L8 8.6 5.1 10.6 6 7.4 3.5 5.4h3.4z" />
    </svg>
  );
}
