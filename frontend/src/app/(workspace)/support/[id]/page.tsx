"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { buttonClass, fieldClass } from "@/components/auth-card";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { Member, SupportConversation, SupportMessage } from "@/lib/types";

const statuses = ["open", "pending", "resolved", "closed"] as const;
const priorities = ["low", "normal", "high", "urgent"] as const;

export default function SupportConversationPage() {
  const params = useParams<{ id: string }>();
  const conversationId = params.id;
  const { organizationId } = useSession();
  const [conversation, setConversation] = useState<SupportConversation | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [draftText, setDraftText] = useState("");
  const [reply, setReply] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!organizationId || !conversationId) return;
    const nextConversation = await api<SupportConversation>(`/support/conversations/${conversationId}`);
    setConversation(nextConversation);
    const open = nextConversation.messages.find((message) => message.author_type === "ai" && message.draft_status === "draft");
    setDraftText(open?.content ?? "");
    if (nextConversation.draft_error) setError(nextConversation.draft_error);
    try {
      setMembers(await api<Member[]>(`/organizations/${organizationId}/members`));
    } catch {
      setMembers([]);
    }
  }

  useEffect(() => {
    if (!organizationId) return;
    load().catch((caught) => setError(caught instanceof ApiError ? caught.message : "The conversation could not be loaded."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId, conversationId]);

  const openDraft = conversation?.messages.find((message) => message.author_type === "ai" && message.draft_status === "draft");

  async function run(action: () => Promise<SupportConversation>) {
    setBusy(true);
    setError(null);
    try {
      const next = await action();
      setConversation(next);
      const open = next.messages.find((message) => message.author_type === "ai" && message.draft_status === "draft");
      setDraftText(open?.content ?? "");
      if (next.draft_error) setError(next.draft_error);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "That change could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  if (!conversation) {
    return (
      <section>
        <Link href="/support" className="text-sm text-muted">
          Back to support
        </Link>
        <p className="mt-4 text-sm text-muted">{error || "Loading…"}</p>
      </section>
    );
  }

  return (
    <section>
      <Link href="/support" className="text-sm text-muted">
        Back to support
      </Link>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{conversation.subject}</h1>
          <p className="mt-1 text-sm capitalize text-muted">
            {conversation.status}
            {conversation.escalated ? " · escalated" : ""} · {conversation.priority || "normal"}
          </p>
        </div>
      </div>
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

      <div className="surface-card mt-4 flex flex-wrap items-center gap-2 rounded-lg border border-line p-3">
        <select
          className={`${fieldClass} max-w-xs`}
          value={conversation.status}
          onChange={(event) =>
            run(() =>
              api<SupportConversation>(`/support/conversations/${conversation.id}`, {
                method: "PATCH",
                body: JSON.stringify({ status: event.target.value }),
              }),
            )
          }
        >
          {statuses.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
        <select
          className={`${fieldClass} max-w-xs`}
          value={conversation.priority || "normal"}
          onChange={(event) =>
            run(() =>
              api<SupportConversation>(`/support/conversations/${conversation.id}`, {
                method: "PATCH",
                body: JSON.stringify({ priority: event.target.value }),
              }),
            )
          }
        >
          {priorities.map((priority) => (
            <option key={priority} value={priority}>
              {priority}
            </option>
          ))}
        </select>
        <select
          className={`${fieldClass} max-w-xs`}
          value={conversation.assigned_to || ""}
          onChange={(event) =>
            run(() =>
              api<SupportConversation>(`/support/conversations/${conversation.id}`, {
                method: "PATCH",
                body: JSON.stringify({ assigned_to: event.target.value || null }),
              }),
            )
          }
        >
          <option value="">Unassigned</option>
          {members.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.full_name || member.email}
            </option>
          ))}
        </select>
        <button
          className={buttonClass}
          type="button"
          disabled={busy || conversation.escalated}
          onClick={() =>
            run(() =>
              api<SupportConversation>(`/support/conversations/${conversation.id}`, {
                method: "PATCH",
                body: JSON.stringify({ escalated: true }),
              }),
            )
          }
        >
          Escalate
        </button>
        <button
          className={buttonClass}
          type="button"
          disabled={busy || conversation.status === "resolved"}
          onClick={() =>
            run(() =>
              api<SupportConversation>(`/support/conversations/${conversation.id}`, {
                method: "PATCH",
                body: JSON.stringify({ status: "resolved" }),
              }),
            )
          }
        >
          Mark resolved
        </button>
      </div>

      <div className="mt-6 grid gap-3">
        {conversation.messages.map((message) => (
          <MessageCard key={message.id} message={message} />
        ))}
      </div>

      {openDraft ? (
        <div className="surface-card mt-6 rounded-lg border border-line p-4">
          <h2 className="font-medium">Draft, not sent</h2>
          {openDraft.suggest_escalation ? (
            <p className="mt-2 text-sm text-muted">This draft suggests a person should take the conversation.</p>
          ) : null}
          <p className="mt-1 text-xs text-muted">
            {openDraft.provider ? `Drafted by ${openDraft.provider}.` : "Drafted without a provider because the notes were not enough."}
          </p>
          <textarea className={`${fieldClass} mt-3`} rows={5} value={draftText} onChange={(event) => setDraftText(event.target.value)} />
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className={buttonClass}
              type="button"
              disabled={busy}
              onClick={() =>
                run(() =>
                  api<SupportConversation>(`/support/conversations/${conversation.id}/drafts/${openDraft.id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ message: draftText }),
                  }),
                )
              }
            >
              Save edit
            </button>
            <button
              className={buttonClass}
              type="button"
              disabled={busy}
              onClick={() =>
                run(() =>
                  api<SupportConversation>(`/support/conversations/${conversation.id}/drafts/${openDraft.id}/approve`, {
                    method: "POST",
                  }),
                )
              }
            >
              Approve
            </button>
            <button
              className="rounded-md border border-line bg-surface px-4 py-2 text-sm"
              type="button"
              disabled={busy}
              onClick={() =>
                run(() =>
                  api<SupportConversation>(`/support/conversations/${conversation.id}/drafts/${openDraft.id}/reject`, {
                    method: "POST",
                  }),
                )
              }
            >
              Reject
            </button>
            <button
              className="rounded-md border border-line bg-surface px-4 py-2 text-sm"
              type="button"
              disabled={busy}
              onClick={() => run(() => api<SupportConversation>(`/support/conversations/${conversation.id}/drafts`, { method: "POST" }))}
            >
              Request another draft
            </button>
          </div>
        </div>
      ) : (
        <button
          className={`${buttonClass} mt-6`}
          type="button"
          disabled={busy}
          onClick={() => run(() => api<SupportConversation>(`/support/conversations/${conversation.id}/drafts`, { method: "POST" }))}
        >
          Request a draft
        </button>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <form
          className="surface-card rounded-lg border border-line p-4"
          onSubmit={(event) => {
            event.preventDefault();
            const text = reply;
            run(async () => {
              const next = await api<SupportConversation>(`/support/conversations/${conversation.id}/messages`, {
                method: "POST",
                body: JSON.stringify({ message: text }),
              });
              setReply("");
              return next;
            });
          }}
        >
          <h2 className="font-medium">Customer message</h2>
          <textarea className={`${fieldClass} mt-3`} rows={4} value={reply} onChange={(event) => setReply(event.target.value)} placeholder="Add the next customer message" />
          <button className={`${buttonClass} mt-3`} type="submit" disabled={busy || !reply.trim()}>
            Add message
          </button>
        </form>
        <form
          className="surface-card rounded-lg border border-line p-4"
          onSubmit={(event) => {
            event.preventDefault();
            const text = note;
            run(async () => {
              const next = await api<SupportConversation>(`/support/conversations/${conversation.id}/notes`, {
                method: "POST",
                body: JSON.stringify({ message: text }),
              });
              setNote("");
              return next;
            });
          }}
        >
          <h2 className="font-medium">Internal note</h2>
          <p className="mt-1 text-sm text-muted">Visible to the team. It is not part of the customer reply.</p>
          <textarea className={`${fieldClass} mt-3`} rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Note for the team" />
          <button className={`${buttonClass} mt-3`} type="submit" disabled={busy || !note.trim()}>
            Save note
          </button>
        </form>
      </div>
    </section>
  );
}

function MessageCard({ message }: { message: SupportMessage }) {
  const label =
    message.internal
      ? "Internal note"
      : message.author_type === "ai" && message.draft_status === "draft"
        ? "Draft, not sent"
        : message.author_type === "ai" && message.draft_status === "approved"
          ? "Approved reply"
          : message.author_type === "ai" && message.draft_status === "rejected"
            ? "Rejected draft"
            : message.author_type === "system"
              ? "Welcome"
              : "Customer";
  return (
    <article className={`rounded-lg border border-line px-4 py-3 ${message.internal ? "bg-surface" : "surface-card"}`}>
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 whitespace-pre-wrap text-sm">{message.content}</p>
    </article>
  );
}
