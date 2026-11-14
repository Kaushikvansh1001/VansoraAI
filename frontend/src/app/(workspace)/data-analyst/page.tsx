"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { buttonClass, fieldClass } from "@/components/auth-card";
import { ApiError, api, downloadApi } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { AnalystDataset, AnalystResult } from "@/lib/types";

const COLORS = ["#4E6574", "#1C1C1A", "#8A9398", "#C5C1B7"];

export default function DataAnalystPage() {
  const { organization, organizationId } = useSession();
  const [datasets, setDatasets] = useState<AnalystDataset[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [history, setHistory] = useState<AnalystResult[]>([]);
  const [result, setResult] = useState<AnalystResult | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);

  const selected = datasets.find((dataset) => dataset.id === selectedId) ?? null;

  function load(orgId: string) {
    return api<AnalystDataset[]>("/analyst/datasets", { orgId }).then((rows) => {
      setDatasets(rows);
      setSelectedId((current) => current ?? rows.find((row) => row.status === "ready")?.id ?? rows[0]?.id ?? null);
    });
  }

  useEffect(() => {
    if (!organizationId) return;
    let active = true;
    load(organizationId).catch((caught) => {
      if (active) setError(caught instanceof ApiError ? caught.message : "Could not load datasets.");
    });
    return () => {
      active = false;
    };
  }, [organizationId]);

  useEffect(() => {
    if (!organizationId || !selectedId) {
      setHistory([]);
      return;
    }
    let active = true;
    api<AnalystResult[]>(`/analyst/datasets/${selectedId}/analyses`, { orgId: organizationId })
      .then((rows) => {
        if (active) setHistory(rows);
      })
      .catch(() => {
        if (active) setHistory([]);
      });
    return () => {
      active = false;
    };
  }, [organizationId, selectedId]);

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!organizationId) return;
    if (!file) {
      setError("Choose a spreadsheet first.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.set("file", file);
      const dataset = await api<AnalystDataset>("/analyst/datasets", { method: "POST", orgId: organizationId, body });
      if (dataset.status === "failed") setError(dataset.error_message ?? "The file could not be read.");
      setSelectedId(dataset.id);
      setFile(null);
      setFileKey((value) => value + 1);
      await load(organizationId);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The file could not be uploaded.");
    } finally {
      setUploading(false);
    }
  }

  async function onAsk(event: FormEvent) {
    event.preventDefault();
    if (!organizationId || !selected) return;
    if (selected.status !== "ready") {
      setError("Wait until the dataset says ready.");
      return;
    }
    if (question.trim().length < 2) {
      setError("Write a question first.");
      return;
    }
    setAsking(true);
    setError(null);
    try {
      const body = await api<AnalystResult>(`/analyst/datasets/${selected.id}/ask`, {
        method: "POST",
        orgId: organizationId,
        body: JSON.stringify({ question }),
      });
      setResult(body);
      if (body.status === "failed") setError(body.error_message ?? "The question could not be answered.");
      setHistory(await api<AnalystResult[]>(`/analyst/datasets/${selected.id}/analyses`, { orgId: organizationId }));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The question could not be answered.");
    } finally {
      setAsking(false);
    }
  }

  async function download(path: string, filename: string) {
    if (!organizationId) return;
    setError(null);
    try {
      await downloadApi(path, filename, organizationId);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The file could not be downloaded.");
    }
  }

  async function removeDataset(datasetId: string) {
    if (!organizationId) return;
    setError(null);
    try {
      await api(`/analyst/datasets/${datasetId}`, { method: "DELETE", orgId: organizationId });
      if (selectedId === datasetId) {
        setSelectedId(null);
        setResult(null);
      }
      await load(organizationId);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The dataset could not be deleted.");
    }
  }

  async function removeAnalysis(analysisId: string) {
    if (!organizationId) return;
    setError(null);
    try {
      await api(`/analyst/analyses/${analysisId}`, { method: "DELETE", orgId: organizationId });
      setHistory((current) => current.filter((item) => item.id !== analysisId));
      if (result?.id === analysisId) setResult(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The analysis could not be deleted.");
    }
  }

  if (!organization) {
    return (
      <section className="max-w-lg">
        <h1 className="text-2xl font-semibold">Data analyst</h1>
        <p className="mt-2 text-muted">Create an organization before uploading a spreadsheet.</p>
        <Link href="/settings" className="mt-4 inline-block text-sm font-medium text-ink">
          Create an organization
        </Link>
      </section>
    );
  }

  const columns = selected?.profile.columns ?? [];
  const preview = selected?.profile.preview ?? [];

  return (
    <section className="max-w-5xl">
      <h1 className="text-2xl font-semibold">Data analyst</h1>
      <p className="mt-2 text-sm text-muted">
        Upload a spreadsheet. Numbers are calculated from the file. The written note underneath is an interpretation.
      </p>
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

      <form className="surface-card mt-6 rounded-lg border border-line p-4" onSubmit={onUpload}>
        <h2 className="text-sm font-medium">Upload a dataset</h2>
        <p className="mt-1 text-sm text-muted">CSV, XLSX, or XLS. Maximum 5 MB and 20,000 rows.</p>
        <input
          key={fileKey}
          className="mt-3 block text-sm"
          type="file"
          accept=".csv,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <button className={`${buttonClass} mt-3`} disabled={uploading} type="submit">
          {uploading ? "Reading…" : "Upload"}
        </button>
      </form>

      <div className="mt-4 grid gap-3">
        {datasets.length === 0 ? <p className="text-sm text-muted">No datasets yet.</p> : null}
        {datasets.map((dataset) => (
          <article key={dataset.id} className={`surface-card rounded-lg border p-4 ${dataset.id === selectedId ? "border-ink/20" : "border-line"}`}>
            <div className="flex items-baseline justify-between gap-3">
              <button className="text-left font-medium" type="button" onClick={() => { setSelectedId(dataset.id); setResult(null); }}>
                {dataset.name}
              </button>
              <span className="text-sm text-muted">{dataset.status}</span>
            </div>
            <p className="mt-1 text-sm text-muted">{dataset.row_count} rows · {dataset.column_count} columns</p>
            {dataset.error_message ? <p className="mt-2 text-sm text-red-700">{dataset.error_message}</p> : null}
            <div className="mt-3 flex gap-3 text-sm">
              <button type="button" onClick={() => download(`/analyst/datasets/${dataset.id}/summary.csv`, `${dataset.name}-summary.csv`)}>
                Export summary
              </button>
              <button type="button" onClick={() => removeDataset(dataset.id)}>Delete</button>
            </div>
          </article>
        ))}
      </div>

      {selected && selected.status === "ready" ? (
        <div className="mt-8">
          <h2 className="text-lg font-semibold">{selected.name}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <Metric label="Rows" value={String(selected.row_count)} />
            <Metric label="Columns" value={String(selected.column_count)} />
            <Metric label="Duplicate rows" value={String(selected.profile.duplicate_rows ?? 0)} />
          </div>
          <div className="mt-4 overflow-x-auto rounded-lg border border-line">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-secondary text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Column</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium">Missing</th>
                  <th className="px-3 py-2 font-medium">Unique</th>
                  <th className="px-3 py-2 font-medium">Range</th>
                </tr>
              </thead>
              <tbody>
                {columns.map((column) => (
                  <tr key={column.name} className="border-t border-line">
                    <td className="px-3 py-2">{column.name}</td>
                    <td className="px-3 py-2">{column.type}</td>
                    <td className="px-3 py-2">{column.missing}</td>
                    <td className="px-3 py-2">{column.unique}</td>
                    <td className="px-3 py-2 text-muted">{rangeText(column)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.length > 0 ? (
            <div className="mt-4 overflow-x-auto rounded-lg border border-line">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-secondary text-muted">
                  <tr>
                    {columns.map((column) => (
                      <th key={column.name} className="px-3 py-2 font-medium">{column.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.map((row, index) => (
                    <tr key={index} className="border-t border-line">
                      {columns.map((column) => (
                        <td key={column.name} className="px-3 py-2">{String(row[column.name] ?? "")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <form className="mt-8" onSubmit={onAsk}>
            <h2 className="text-sm font-medium">Ask about this dataset</h2>
            <textarea
              className={`${fieldClass} mt-3 min-h-24`}
              value={question}
              maxLength={1000}
              placeholder="What is the total revenue?"
              onChange={(event) => setQuestion(event.target.value)}
            />
            <button className={`${buttonClass} mt-3`} disabled={asking} type="submit">
              {asking ? "Calculating…" : "Ask"}
            </button>
          </form>

          {result && result.status === "succeeded" ? (
            <div className="mt-5 grid gap-4">
              <ResultView result={result} />
              <div className="flex gap-3 text-sm">
                <button type="button" onClick={() => download(`/analyst/analyses/${result.id}/export.csv`, "analysis.csv")}>
                  Export CSV
                </button>
                <button type="button" onClick={() => download(`/analyst/analyses/${result.id}/report.pdf`, "analysis-report.pdf")}>
                  Export PDF
                </button>
              </div>
            </div>
          ) : null}

          <div className="mt-8">
            <h2 className="text-sm font-medium">History</h2>
            <div className="mt-3 grid gap-2">
              {history.length === 0 ? <p className="text-sm text-muted">No questions yet.</p> : null}
              {history.map((item) => (
                <article key={item.id} className="rounded-lg border border-line px-3 py-2 text-sm">
                  <button className="text-left" type="button" onClick={() => setResult(item)}>
                    {item.question}
                  </button>
                  <div className="mt-1 flex items-center justify-between text-muted">
                    <span>{item.status}</span>
                    <button type="button" onClick={() => removeAnalysis(item.id)}>Delete</button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="surface-card rounded-lg border border-line p-4">
      <p className="text-xs font-medium tracking-wide text-muted">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </article>
  );
}

function rangeText(column: { type: string; numeric: { min: number; max: number } | null; date_min: string | null; date_max: string | null }) {
  if (column.numeric) return `${column.numeric.min} – ${column.numeric.max}`;
  if (column.date_min) return `${column.date_min} – ${column.date_max}`;
  return "—";
}

function ResultView({ result }: { result: AnalystResult }) {
  return (
    <>
      <article className="surface-card rounded-lg border border-ink/15 p-5">
        <p className="text-xs font-medium tracking-wide text-muted">Calculated</p>
        <ul className="mt-3 grid gap-2 text-lg leading-relaxed">
          {result.facts.map((fact) => (
            <li key={fact}>{fact}</li>
          ))}
        </ul>
        {result.chart ? <ChartView chart={result.chart} /> : null}
      </article>
      <article className="surface-card rounded-lg border border-line p-5">
        <p className="text-xs font-medium tracking-wide text-muted">Written by the model</p>
        <p className="mt-2 text-sm leading-relaxed">{result.interpretation}</p>
      </article>
      {result.insights.length > 0 ? (
        <article className="surface-card rounded-lg border border-line p-5">
          <p className="text-xs font-medium tracking-wide text-muted">From the file</p>
          <ul className="mt-3 grid gap-2 text-sm">
            {result.insights.map((insight) => (
              <li key={insight}>{insight}</li>
            ))}
          </ul>
        </article>
      ) : null}
    </>
  );
}

function ChartView({ chart }: { chart: NonNullable<AnalystResult["chart"]> }) {
  if (chart.type === "kpi") {
    const row = chart.data[0];
    return (
      <p className="mt-4 text-3xl font-semibold">
        {formatNumber(row?.value)} <span className="text-base font-normal text-muted">{row?.label}</span>
      </p>
    );
  }
  if (chart.type === "table" || chart.data.length === 0) {
    return (
      <table className="mt-4 min-w-full text-left text-sm">
        <tbody>
          {chart.data.map((row) => (
            <tr key={row.label} className="border-t border-line">
              <td className="py-2">{row.label}</td>
              <td className="py-2 text-right">{formatNumber(row.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return (
    <div className="mt-4 h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        {chart.type === "line" ? (
          <LineChart data={chart.data}>
            <XAxis dataKey="label" stroke="#5E5E59" fontSize={12} />
            <YAxis stroke="#5E5E59" fontSize={12} />
            <Tooltip />
            <Line dataKey="value" stroke="#4E6574" strokeWidth={2} dot={false} />
          </LineChart>
        ) : chart.type === "area" ? (
          <AreaChart data={chart.data}>
            <XAxis dataKey="label" stroke="#5E5E59" fontSize={12} />
            <YAxis stroke="#5E5E59" fontSize={12} />
            <Tooltip />
            <Area dataKey="value" stroke="#4E6574" fill="#4E6574" fillOpacity={0.2} />
          </AreaChart>
        ) : chart.type === "pie" ? (
          <PieChart>
            <Tooltip />
            <Pie data={chart.data} dataKey="value" nameKey="label" outerRadius={90}>
              {chart.data.map((row, index) => (
                <Cell key={row.label} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        ) : (
          <BarChart data={chart.data}>
            <XAxis dataKey="label" stroke="#5E5E59" fontSize={12} />
            <YAxis stroke="#5E5E59" fontSize={12} />
            <Tooltip />
            <Bar dataKey="value" fill="#4E6574" radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function formatNumber(value: number | undefined) {
  if (value === undefined || value === null) return "0";
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}
