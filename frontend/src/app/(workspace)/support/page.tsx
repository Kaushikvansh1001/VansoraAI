"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { buttonClass, fieldClass } from "@/components/auth-card";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { SupportAssistant, SupportCard, SupportConversation, SupportSummary } from "@/lib/types";

const tones = ["professional", "friendly", "formal", "concise"] as const;
const priorities = ["low", "normal", "high", "urgent"] as const;

const stats: { key: keyof Pick<SupportSummary, "total" | "open" | "pending" | "resolved" | "ai_drafts" | "approved_replies" | "escalated">; label: string }[] = [
  { key: "total", label: "Total conversations" },
  { key: "open", label: "Open" },
  { key: "pending", label: "Pending" },
  { key: "resolved", label: "Resolved" },
  { key: "ai_drafts", label: "AI drafts" },
  { key: "approved_replies", label: "Approved replies" },
  { key: "escalated", label: "Escalated" },
];

const emptyAssistant = {
  name: "",
  description: "",
  welcome_message: "",
  instructions: "",
  tone: "professional" as SupportAssistant["tone"],
  language: "English",
  enabled: true,
};

export default function SupportPage() {
  const router = useRouter();
  const { organizationId } = useSession();
  const [summary, setSummary] = useState<SupportSummary | null>(null);
  const [assistants, setAssistants] = useState<SupportAssistant[]>([]);
  const [conversations, setConversations] = useState<SupportCard[]>([]);
  const [form, setForm] = useState(emptyAssistant);
  const [editing, setEditing] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [priority, setPriority] = useState<(typeof priorities)[number]>("normal");
  const [assistantId, setAssistantId] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [escalatedOnly, setEscalatedOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function load(search = query, statusFilter = status, priorityLevel = priorityFilter, escalated = escalatedOnly) {
    if (!organizationId) return;
    const params = new URLSearchParams();
    if (search.trim()) params.set("q", search.trim());
    if (statusFilter) params.set("status", statusFilter);
    if (priorityLevel) params.set("priority", priorityLevel);
    if (escalated) params.set("escalated", "true");
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const [nextSummary, nextAssistants, nextConversations] = await Promise.all([
      api<SupportSummary>("/support/summary"),
      api<SupportAssistant[]>("/support/assistants"),
      api<SupportCard[]>(`/support/conversations${suffix}`),
    ]);
    setSummary(nextSummary);
    setAssistants(nextAssistants);
    setConversations(nextConversations);
    setAssistantId((current) => current || nextAssistants.find((item) => item.enabled)?.id || "");
  }

  useEffect(() => {
    if (!organizationId) return;
    load().catch((caught) => setError(caught instanceof ApiError ? caught.message : "Support could not be loaded."));
    // The first load uses the empty filters. Later searches call load directly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId]);

  if (!organizationId) {
    return (
      <section>
        <h1 className="text-2xl font-semibold">Support</h1>
        <p className="mt-2 text-muted">Create an organization before conversations have a place to live.</p>
        <Link href="/settings" className="mt-4 inline-block text-sm font-medium">
          Create an organization
        </Link>
      </section>
    );
  }

  async function saveAssistant() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const body = {
        ...form,
        description: form.description.trim() ? form.description : null,
      };
      if (editing) {
        await api(`/support/assistants/${editing}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        await api("/support/assistants", { method: "POST", body: JSON.stringify(body) });
      }
      setForm(emptyAssistant);
      setEditing(null);
      setNotice(editing ? "Assistant updated." : "Assistant created.");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The assistant could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function startConversation() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api<SupportConversation>("/support/conversations", {
        method: "POST",
        body: JSON.stringify({ assistant_id: assistantId, subject, message, priority }),
      });
      setSubject("");
      setMessage("");
      if (created.draft_error) {
        setNotice(created.draft_error);
        await load();
      } else {
        router.push(`/support/${created.id}`);
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The conversation could not be started.");
    } finally {
      setSaving(false);
    }
  }

  function editAssistant(assistant: SupportAssistant) {
    setEditing(assistant.id);
    setForm({
      name: assistant.name,
      description: assistant.description || "",
      welcome_message: assistant.welcome_message,
      instructions: assistant.instructions,
      tone: assistant.tone,
      language: assistant.language,
      enabled: assistant.enabled,
    });
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Support</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Drafts stay in the conversation until a person approves them. Approved replies are not emailed.
      </p>
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="mt-4 text-sm text-muted">{notice}</p> : null}
      {!summary && !error ? <p className="mt-4 text-sm text-muted">Loading…</p> : null}

      {summary ? (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {stats.map((stat) => (
              <article key={stat.key} className="surface-card rounded-lg border border-line p-4">
                <p className="text-sm text-muted">{stat.label}</p>
                <p className="mt-2 text-2xl font-semibold">{summary[stat.key]}</p>
              </article>
            ))}
            <article className="surface-card rounded-lg border border-line p-4">
              <p className="text-sm text-muted">Average response</p>
              <p className="mt-2 text-2xl font-semibold">{responseLabel(summary.average_response_seconds)}</p>
              <p className="mt-1 text-xs text-muted">From the first customer message to the first approved reply.</p>
            </article>
          </div>
          <p className="mt-3 text-sm text-muted">
            {summary.providers.length
              ? `Provider drafts: ${summary.providers.map((item) => `${item.provider} ${item.drafts}`).join(", ")}.`
              : "No AI provider has drafted a reply yet."}{" "}
            AI drafts count every generated reply. Approved replies count only what a person kept.
            {summary.closed ? ` Closed conversations: ${summary.closed}.` : ""}
          </p>
        </>
      ) : null}

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div>
          <h2 className="font-medium">Conversations</h2>
          <form
            className="surface-card mt-3 grid items-center gap-2 rounded-lg border border-line p-3 md:grid-cols-[minmax(0,1fr)_150px_150px_auto_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              load().catch((caught) => setError(caught instanceof ApiError ? caught.message : "The list could not be filtered."));
            }}
          >
            <input className={fieldClass} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search subject or message" />
            <select className={fieldClass} value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">Any status</option>
              <option value="open">Open</option>
              <option value="pending">Pending</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>
            <select className={fieldClass} value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}>
              <option value="">Any priority</option>
              {priorities.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={escalatedOnly} onChange={(event) => setEscalatedOnly(event.target.checked)} />
              Escalated
            </label>
            <button className={buttonClass} type="submit">
              Filter
            </button>
          </form>
          {conversations.length === 0 ? <p className="mt-3 text-sm text-muted">No conversations match.</p> : null}
          <ul className="mt-3 grid gap-2">
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <Link href={`/support/${conversation.id}`} className="surface-card block rounded-lg border border-line px-4 py-3">
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-medium">{conversation.subject}</span>
                    <span className="text-sm capitalize text-muted">{conversation.status}</span>
                  </span>
                  <span className="mt-1 block text-xs capitalize text-muted">
                    {conversation.priority || "normal"}
                    {conversation.escalated ? " · escalated" : ""}
                  </span>
                </Link>
              </li>
            ))}
          </ul>

          <h2 className="mt-8 font-medium">Recent activity</h2>
          {summary && summary.recent.length === 0 ? <p className="mt-2 text-sm text-muted">No conversations yet.</p> : null}
          <ul className="mt-3 grid gap-2">
            {summary?.recent.map((item) => (
              <li key={item.id}>
                <Link href={`/support/${item.id}`} className="block rounded-lg border border-line bg-surface px-3 py-2 text-sm">
                  <span className="font-medium">{item.subject}</span>
                  <span className="mt-1 block capitalize text-muted">
                    {item.status}
                    {item.escalated ? " · escalated" : ""}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div className="grid gap-6">
          <div className="surface-card rounded-lg border border-line p-4">
            <h2 className="font-medium">{editing ? "Edit assistant" : "New assistant"}</h2>
            <div className="mt-3 grid gap-2">
              <input className={fieldClass} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Assistant name" />
              <input className={fieldClass} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Description" />
              <textarea className={fieldClass} value={form.welcome_message} onChange={(event) => setForm({ ...form, welcome_message: event.target.value })} placeholder="Welcome message" rows={2} />
              <textarea className={fieldClass} value={form.instructions} onChange={(event) => setForm({ ...form, instructions: event.target.value })} placeholder="System instructions" rows={4} />
              <select className={fieldClass} value={form.tone} onChange={(event) => setForm({ ...form, tone: event.target.value as SupportAssistant["tone"] })}>
                {tones.map((tone) => (
                  <option key={tone} value={tone}>
                    {tone}
                  </option>
                ))}
              </select>
              <input className={fieldClass} value={form.language} onChange={(event) => setForm({ ...form, language: event.target.value })} placeholder="Language" />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />
                Enabled
              </label>
              <button className={buttonClass} type="button" onClick={saveAssistant} disabled={saving}>
                {saving ? "Saving…" : editing ? "Update assistant" : "Create assistant"}
              </button>
              {editing ? (
                <button
                  className="text-sm text-muted"
                  type="button"
                  onClick={() => {
                    setEditing(null);
                    setForm(emptyAssistant);
                  }}
                >
                  Cancel edit
                </button>
              ) : null}
            </div>
            <ul className="mt-4 grid gap-2">
              {assistants.map((assistant) => (
                <li key={assistant.id}>
                  <button type="button" className="w-full rounded-md border border-line px-3 py-2 text-left text-sm" onClick={() => editAssistant(assistant)}>
                    <span className="font-medium">{assistant.name}</span>
                    <span className="mt-1 block capitalize text-muted">
                      {assistant.tone} · {assistant.language} · {assistant.enabled ? "enabled" : "disabled"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="surface-card rounded-lg border border-line p-4">
            <h2 className="font-medium">Start a conversation</h2>
            <div className="mt-3 grid gap-2">
              <select className={fieldClass} value={assistantId} onChange={(event) => setAssistantId(event.target.value)}>
                <option value="">Choose an assistant</option>
                {assistants.filter((assistant) => assistant.enabled).map((assistant) => (
                  <option key={assistant.id} value={assistant.id}>
                    {assistant.name}
                  </option>
                ))}
              </select>
              <input className={fieldClass} value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Subject" />
              <textarea className={fieldClass} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Customer message" rows={4} />
              <select className={fieldClass} value={priority} onChange={(event) => setPriority(event.target.value as (typeof priorities)[number])}>
                {priorities.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <button className={buttonClass} type="button" onClick={startConversation} disabled={saving || !assistantId}>
                Start conversation
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function responseLabel(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds} sec`;
  return `${Math.round(seconds / 60)} min`;
}
