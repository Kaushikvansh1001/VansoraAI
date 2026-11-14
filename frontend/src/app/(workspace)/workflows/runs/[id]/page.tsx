"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { WorkflowExecution } from "@/lib/types";
import { durationLabel, stepLabel } from "@/lib/workflow-catalog";

export default function WorkflowRunPage() {
  const params = useParams<{ id: string }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;
  const { organizationId } = useSession();
  const [run, setRun] = useState<WorkflowExecution | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!organizationId || !id) return;
    let active = true;
    api<WorkflowExecution>(`/workflows/executions/${id}`, { orgId: organizationId })
      .then((body) => {
        if (active) setRun(body);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof ApiError ? caught.message : "Could not open this run.");
      });
    return () => {
      active = false;
    };
  }, [id, organizationId]);

  return (
    <section className="max-w-3xl">
      <Link href="/workflows" className="text-sm text-muted">
        Workflows
      </Link>
      <h1 className="mt-1 text-2xl font-semibold">{run ? run.workflow_name : "Run"}</h1>
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
      {!run && !error ? <p className="mt-4 text-sm text-muted">Loading…</p> : null}
      {run ? (
        <>
          <p className="mt-2 text-sm text-muted">
            {run.status} · {run.trigger_type} · {durationLabel(run.duration_ms)} · {new Date(run.created_at).toLocaleString()}
          </p>
          {run.error_message ? <p className="mt-3 text-sm text-red-700">{run.error_message}</p> : null}
          {run.workflow_id ? (
            <Link href={`/workflows/${run.workflow_id}`} className="mt-3 inline-block text-sm font-medium">
              Open workflow
            </Link>
          ) : null}
          <ol className="mt-6 grid gap-3">
            {run.steps.map((step, index) => (
              <li key={step.id} className="surface-card rounded-lg border border-line p-4">
                <p className="text-xs text-muted">Step {index + 1}</p>
                <h2 className="font-medium">{step.node_label || step.node_type}</h2>
                <p className="mt-1 text-sm text-muted">
                  {stepLabel(step.status, step.output_json)} · {durationLabel(step.duration_ms)}
                </p>
                {step.error_message ? <p className="mt-2 text-sm text-red-700">{step.error_message}</p> : null}
                {typeof step.output_json?.text === "string" && step.output_json.text ? (
                  <p className="mt-3 whitespace-pre-wrap text-sm">{step.output_json.text}</p>
                ) : null}
                <details className="mt-3 text-sm">
                  <summary className="cursor-pointer text-muted">Node output</summary>
                  <pre className="mt-2 overflow-auto rounded-md bg-secondary p-3 text-xs">{JSON.stringify(step.output_json, null, 2)}</pre>
                </details>
              </li>
            ))}
          </ol>
        </>
      ) : null}
    </section>
  );
}
