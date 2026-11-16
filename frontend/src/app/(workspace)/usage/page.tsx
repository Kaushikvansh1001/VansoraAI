"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { buttonClass } from "@/components/auth-card";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { AiFallback, AiProviders, AiTestResult, AiUsage } from "@/lib/types";

export default function UsagePage() {
  const { organization, organizationId } = useSession();
  const [providers, setProviders] = useState<AiProviders | null>(null);
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const [fallbacks, setFallbacks] = useState<AiFallback[]>([]);
  const [prompt, setPrompt] = useState("Reply with one short sentence.");
  const [result, setResult] = useState<AiTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function load(orgId: string) {
    return Promise.all([
      api<AiProviders>("/ai/providers", { orgId }),
      api<AiUsage>("/ai/usage", { orgId }),
      api<AiFallback[]>("/ai/fallbacks", { orgId }),
    ]).then(([providerBody, usageBody, fallbackBody]) => {
      setProviders(providerBody);
      setUsage(usageBody);
      setFallbacks(fallbackBody);
    });
  }

  useEffect(() => {
    if (!organizationId || organization?.role !== "org_admin") {
      return;
    }
    let active = true;
    load(organizationId).catch((caught) => {
      if (!active) return;
      setError(caught instanceof ApiError ? caught.message : "Could not load provider status.");
    });
    return () => {
      active = false;
    };
  }, [organizationId, organization?.role]);

  async function onTest(event: FormEvent) {
    event.preventDefault();
    if (!organizationId) return;
    setPending(true);
    setError(null);
    setResult(null);
    try {
      const body = await api<AiTestResult>("/ai/test", {
        method: "POST",
        orgId: organizationId,
        body: JSON.stringify({ prompt }),
      });
      setResult(body);
      await load(organizationId);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The test request failed.");
    } finally {
      setPending(false);
    }
  }

  if (!organization) {
    return (
      <section className="max-w-lg">
        <h1 className="text-2xl font-semibold">AI providers</h1>
        <p className="mt-2 text-muted">Create an organization before provider status can be read.</p>
        <Link href="/settings" className="mt-4 inline-block text-sm font-medium text-ink">
          Create an organization
        </Link>
      </section>
    );
  }

  if (organization.role !== "org_admin") {
    return (
      <section className="max-w-lg">
        <h1 className="text-2xl font-semibold">AI providers</h1>
        <p className="mt-2 text-muted">Only an organization admin can view provider health and usage.</p>
      </section>
    );
  }

  return (
    <section className="max-w-4xl">
      <h1 className="text-2xl font-semibold">AI providers</h1>
      <p className="mt-1 text-sm text-muted">
        Health comes from each provider. Counts come from this organization&apos;s usage records. Costs are list-price
        estimates, not invoices.
      </p>
      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
      {!providers && !error ? <p className="mt-4 text-sm text-muted">Loading…</p> : null}

      {providers ? (
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {providers.providers.map((provider) => (
            <article key={provider.provider} className="surface-card rounded-lg border border-line p-4">
              <div className="flex items-center justify-between">
                <h2 className="font-medium capitalize">{provider.provider}</h2>
                {provider.active ? <span className="text-xs font-medium text-steel">Active</span> : null}
              </div>
              <p className="mt-2 text-sm">{provider.model}</p>
              <p className="mt-1 text-sm capitalize text-muted">{provider.status.replaceAll("_", " ")}</p>
              {provider.detail ? <p className="mt-2 text-sm text-muted">{provider.detail}</p> : null}
              <p className="mt-3 text-xs text-muted">
                {provider.configured ? "Key or endpoint configured" : "Not configured"}
              </p>
            </article>
          ))}
        </div>
      ) : null}

      {usage ? (
        <div className="mt-6 grid gap-3 sm:grid-cols-4">
          <Metric label="Succeeded" value={String(usage.requests_succeeded)} />
          <Metric label="Failed" value={String(usage.requests_failed)} />
          <Metric label="Tokens" value={String(usage.input_tokens + usage.output_tokens)} />
          <Metric label="Estimated USD" value={usage.estimated_cost_usd} />
        </div>
      ) : null}

      <section className="mt-8">
        <h2 className="font-medium">Fallback history</h2>
        {fallbacks.length === 0 ? (
          <p className="mt-2 text-sm text-muted">No failed requests or fallbacks have been recorded.</p>
        ) : (
          <ul className="surface-card mt-3 divide-y divide-line rounded-lg border border-line">
            {fallbacks.map((row) => (
              <li key={`${row.created_at}-${row.provider}-${row.status}`} className="px-4 py-3 text-sm">
                <span className="font-medium">{row.provider}</span> {row.status}
                {row.error_category ? ` · ${row.error_category}` : ""}
                {row.fallback_from ? ` · fallback from ${row.fallback_from}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>

      <form className="surface-card mt-6 grid gap-3 rounded-lg border border-line p-4" onSubmit={onTest}>
        <h2 className="font-medium">Test a prompt</h2>
        <textarea
          className="field w-full text-sm"
          value={prompt}
          maxLength={500}
          onChange={(event) => setPrompt(event.target.value)}
        />
        <button className={buttonClass} disabled={pending} type="submit">
          {pending ? "Sending…" : "Send test"}
        </button>
        {result ? (
          <p className="text-sm">
            {result.text}{" "}
            <span className="text-muted">
              via {result.provider}
              {result.fallback_from ? `, fallback from ${result.fallback_from}` : ""}. {result.tokens_source} tokens.
              Estimated ${result.estimated_cost_usd}.
            </span>
          </p>
        ) : null}
      </form>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="surface-card rounded-lg border border-line p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}
