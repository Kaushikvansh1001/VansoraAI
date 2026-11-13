"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Dashboard } from "@/lib/types";

const stats: { key: keyof Dashboard; label: string }[] = [
  { key: "documents", label: "Documents" },
  { key: "conversations", label: "Conversations" },
  { key: "queries", label: "AI queries" },
  { key: "workflows", label: "Workflows" },
  { key: "successful_executions", label: "Successful runs" },
  { key: "input_tokens", label: "Input tokens" },
  { key: "output_tokens", label: "Output tokens" },
];

export default function DashboardPage() {
  const { organization, organizationId } = useSession();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!organizationId) {
      setData(null);
      return;
    }
    let active = true;
    api<Dashboard>("/dashboard", { orgId: organizationId })
      .then((body) => {
        if (active) setData(body);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof ApiError ? caught.message : "Could not load the dashboard.");
      });
    return () => {
      active = false;
    };
  }, [organizationId]);

  if (!organization) {
    return (
      <section className="max-w-lg">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-2 text-muted">Create an organization before the counts have a tenant to read.</p>
        <Link href="/settings" className="mt-4 inline-block text-sm text-brand">
          Create an organization
        </Link>
      </section>
    );
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">{organization.name}</h1>
      <p className="mt-1 text-sm text-muted">Counts are read from this organization&apos;s records.</p>
      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
      {!data && !error ? <p className="mt-4 text-sm text-muted">Loading…</p> : null}
      {data ? (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {stats.map((stat) => (
              <article key={stat.key} className="rounded-lg border border-line bg-surface p-4">
                <p className="text-sm text-muted">{stat.label}</p>
                <p className="mt-2 text-2xl font-semibold">{data[stat.key] as number}</p>
              </article>
            ))}
            <article className="rounded-lg border border-line bg-surface p-4">
              <p className="text-sm text-muted">Estimated cost (USD)</p>
              <p className="mt-2 text-2xl font-semibold">{data.estimated_cost_usd}</p>
            </article>
          </div>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <article className="rounded-lg border border-line bg-surface p-4">
              <h2 className="font-medium">Document status</h2>
              <ul className="mt-3 grid grid-cols-2 gap-2 text-sm">
                {Object.entries(data.document_status).map(([status, count]) => (
                  <li key={status} className="flex justify-between rounded-md border border-line px-3 py-2">
                    <span className="capitalize">{status}</span>
                    <span>{count}</span>
                  </li>
                ))}
              </ul>
            </article>
            <article className="rounded-lg border border-line bg-surface p-4">
              <h2 className="font-medium">Recent activity</h2>
              {data.recent_activity.length === 0 ? (
                <p className="mt-3 text-sm text-muted">No activity yet.</p>
              ) : (
                <ul className="mt-3 grid gap-2 text-sm">
                  {data.recent_activity.map((item) => (
                    <li key={`${item.action}-${item.created_at}`} className="flex justify-between gap-3">
                      <span>{item.action}</span>
                      <span className="text-muted">{new Date(item.created_at).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          </div>
          <article className="mt-4 rounded-lg border border-line bg-surface p-4">
            <h2 className="font-medium">Recent conversations</h2>
            {data.recent_conversations.length === 0 ? (
              <p className="mt-3 text-sm text-muted">No conversations yet. The knowledge assistant arrives in a later phase.</p>
            ) : (
              <ul className="mt-3 text-sm">
                {data.recent_conversations.map((item) => (
                  <li key={item.id}>{item.title}</li>
                ))}
              </ul>
            )}
          </article>
        </>
      ) : null}
    </section>
  );
}
