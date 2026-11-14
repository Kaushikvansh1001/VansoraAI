"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { buttonClass } from "@/components/auth-card";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { WorkflowCard, WorkflowSummary } from "@/lib/types";
import { durationLabel } from "@/lib/workflow-catalog";

const stats: { key: keyof Pick<WorkflowSummary, "total" | "active" | "draft" | "paused" | "successful_executions" | "failed_executions">; label: string }[] = [
  { key: "total", label: "Total workflows" },
  { key: "active", label: "Active" },
  { key: "draft", label: "Draft" },
  { key: "paused", label: "Paused" },
  { key: "successful_executions", label: "Successful runs" },
  { key: "failed_executions", label: "Failed runs" },
];

export default function WorkflowsPage() {
  const router = useRouter();
  const { organization, organizationId } = useSession();
  const [summary, setSummary] = useState<WorkflowSummary | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);

  useEffect(() => {
    if (!organizationId) return;
    let active = true;
    Promise.all([
      api<WorkflowSummary>("/workflows/summary", { orgId: organizationId }),
      api<WorkflowCard[]>("/workflows", { orgId: organizationId }),
    ])
      .then(([counts, rows]) => {
        if (!active) return;
        setSummary(counts);
        setWorkflows(rows);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof ApiError ? caught.message : "Could not load workflows.");
      });
    return () => {
      active = false;
    };
  }, [organizationId]);

  async function useTemplate(templateId: string) {
    if (!organizationId) return;
    setCreating(templateId);
    setError(null);
    try {
      const workflow = await api<{ id: string }>("/workflows/from-template", {
        method: "POST",
        orgId: organizationId,
        body: JSON.stringify({ template_id: templateId }),
      });
      router.push(`/workflows/${workflow.id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The template could not be created.");
      setCreating(null);
    }
  }

  if (!organization) {
    return (
      <section className="max-w-lg">
        <h1 className="text-2xl font-semibold">Workflows</h1>
        <p className="mt-2 text-muted">Create an organization before automations have a place to live.</p>
        <Link href="/settings" className="mt-4 inline-block text-sm font-medium">
          Create an organization
        </Link>
      </section>
    );
  }

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Workflows</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Draw a workflow and press Run. Nothing starts on its own, and a run stays inside one request.
          </p>
        </div>
        <Link href="/workflows/new" className={buttonClass}>
          Create workflow
        </Link>
      </div>
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
      {!summary && !error ? <p className="mt-4 text-sm text-muted">Loading…</p> : null}
      {summary ? (
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {stats.map((stat) => (
            <article key={stat.key} className="surface-card rounded-lg border border-line p-4">
              <p className="text-sm text-muted">{stat.label}</p>
              <p className="mt-2 text-2xl font-semibold">{summary[stat.key]}</p>
            </article>
          ))}
        </div>
      ) : null}

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <h2 className="font-medium">Your workflows</h2>
          {workflows.length === 0 ? <p className="mt-2 text-sm text-muted">No workflows yet. Create one or start from a template.</p> : null}
          <ul className="mt-3 grid gap-2">
            {workflows.map((workflow) => (
              <li key={workflow.id}>
                <Link href={`/workflows/${workflow.id}`} className="surface-card block rounded-lg border border-line px-4 py-3">
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-medium">{workflow.name}</span>
                    <span className="text-sm capitalize text-muted">{workflow.status}</span>
                  </span>
                  {workflow.description ? <span className="mt-1 block text-sm text-muted">{workflow.description}</span> : null}
                  <span className="mt-2 block text-xs text-muted">{workflow.node_count} nodes</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="font-medium">Recent runs</h2>
          {summary && summary.recent_executions.length === 0 ? <p className="mt-2 text-sm text-muted">No workflows have been run yet.</p> : null}
          <ul className="mt-3 grid gap-2">
            {summary?.recent_executions.map((run) => (
              <li key={run.id}>
                <Link href={`/workflows/runs/${run.id}`} className="block rounded-lg border border-line bg-surface px-3 py-2 text-sm">
                  <span className="font-medium">{run.workflow_name}</span>
                  <span className="mt-1 block capitalize text-muted">
                    {run.status} · {run.trigger_type} · {durationLabel(run.duration_ms)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <h2 className="mt-8 font-medium">Templates</h2>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {summary?.templates.map((template) => (
          <article key={template.id} className="surface-card rounded-lg border border-line p-4">
            <h3 className="font-medium">{template.name}</h3>
            <p className="mt-2 text-sm text-muted">{template.description}</p>
            <button type="button" className={`${buttonClass} mt-4`} onClick={() => useTemplate(template.id)} disabled={creating === template.id}>
              {creating === template.id ? "Creating…" : "Use template"}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
