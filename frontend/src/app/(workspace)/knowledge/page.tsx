"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { buttonClass, fieldClass } from "@/components/auth-card";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { KnowledgeAnswer, KnowledgeDocument, KnowledgeMode } from "@/lib/types";

export default function KnowledgePage() {
  const { organization, organizationId } = useSession();
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<KnowledgeAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [demo, setDemo] = useState(false);
  const [notice, setNotice] = useState("Upload a PDF or Word file, then ask a question. Answers use that file and name the source.");

  function load(orgId: string) {
    return api<KnowledgeDocument[]>("/knowledge/documents", { orgId }).then(setDocuments);
  }

  useEffect(() => {
    if (!organizationId) {
      setDocuments([]);
      return;
    }
    let active = true;
    api<KnowledgeMode>("/knowledge/mode", { orgId: organizationId })
      .then((mode) => {
        if (!active) return;
        setDemo(mode.demo);
        setNotice(mode.notice);
      })
      .catch((caught) => {
        if (!active) return;
        setError(caught instanceof ApiError ? caught.message : "Could not load documents.");
      });
    load(organizationId).catch((caught) => {
      if (!active) return;
      setError(caught instanceof ApiError ? caught.message : "Could not load documents.");
    });
    return () => {
      active = false;
    };
  }, [organizationId]);

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!organizationId) return;
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.set("file", file);
      const document = await api<KnowledgeDocument>("/knowledge/documents", {
        method: "POST",
        orgId: organizationId,
        body,
      });
      if (document.status === "failed") {
        setError(document.error_message ?? "The file could not be read.");
      }
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
    if (!organizationId) return;
    if (!demo && !ready) {
      setError("Upload a document and wait until it says ready.");
      return;
    }
    if (question.trim().length < 2) {
      setError("Write a question first.");
      return;
    }
    setAsking(true);
    setError(null);
    setAnswer(null);
    try {
      const body = await api<KnowledgeAnswer>("/knowledge/ask", {
        method: "POST",
        orgId: organizationId,
        body: JSON.stringify({ question }),
      });
      setAnswer(body);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The question could not be answered.");
    } finally {
      setAsking(false);
    }
  }

  if (!organization) {
    return (
      <section className="max-w-lg">
        <h1 className="text-2xl font-semibold">Knowledge</h1>
        <p className="mt-2 text-muted">Create an organization before uploading documents.</p>
        <Link href="/settings" className="mt-4 inline-block text-sm font-medium text-ink">
          Create an organization
        </Link>
      </section>
    );
  }

  const ready = documents.some((document) => document.status === "ready");

  return (
    <section className="max-w-3xl">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-2xl font-semibold">Knowledge</h1>
        {demo ? <span className="rounded-md border border-line px-2 py-1 text-xs font-medium tracking-wide text-muted">Demo mode</span> : null}
      </div>
      <p className="mt-2 text-sm text-muted">{notice}</p>
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

      {demo ? null : <form className="surface-card mt-6 rounded-lg border border-line p-4" onSubmit={onUpload}>
        <h2 className="text-sm font-medium">Upload a document</h2>
        <p className="mt-1 text-sm text-muted">PDF, Word (.docx), .txt, .md, or .csv. Maximum 2 MB.</p>
        <input
          key={fileKey}
          className="mt-3 block text-sm"
          type="file"
          accept=".txt,.md,.csv,.pdf,.docx,text/plain,text/markdown,text/csv,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <button className={`${buttonClass} mt-3`} disabled={uploading} type="submit">
          {uploading ? "Reading…" : "Upload"}
        </button>
      </form>}

      <div className="mt-4 grid gap-3">
        {documents.length === 0 ? <p className="text-sm text-muted">No documents yet.</p> : null}
        {documents.map((document) => (
          <article key={document.id} className="surface-card rounded-lg border border-line p-4">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-medium">{document.filename}</h2>
              <span className="text-sm text-muted">{document.status}</span>
            </div>
            {document.error_message ? <p className="mt-2 text-sm text-red-700">{document.error_message}</p> : null}
          </article>
        ))}
      </div>

      <form className="surface-card mt-6 grid gap-3 rounded-lg border border-line p-4" onSubmit={onAsk}>
        <h2 className="text-sm font-medium">Ask about these documents</h2>
        <textarea
          className={fieldClass}
          value={question}
          maxLength={1000}
          placeholder={demo ? "What was Northwind Studio's revenue?" : "What does the file say about refunds?"}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button className={`${buttonClass} mt-3`} disabled={asking} type="submit">
          {asking ? "Answering…" : "Ask"}
        </button>
        {answer ? (
          <div className="mt-5">
            <article className="surface-card rounded-lg border border-ink/15 p-5">
              <p className="text-xs font-medium tracking-wide text-muted">Answer</p>
              <div className="mt-2 text-lg leading-relaxed text-ink">
                <AnswerText text={answer.answer} />
              </div>
              <p className="mt-4 text-sm text-muted">
                {answer.retrieval === "text"
                  ? `Matched by text search in ${sourceNames(answer.citations)}. This is not a semantic vector search.`
                  : `From ${sourceNames(answer.citations)}`}
              </p>
            </article>
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-muted">Passages used</summary>
              <ul className="mt-3 grid gap-2">
                {answer.citations.map((citation) => (
                  <li key={`${citation.document_id}-${citation.chunk_index}`} className="rounded-lg border border-line px-3 py-2 text-sm text-muted">
                    <span className="font-medium text-ink">{citation.filename}</span>
                    <span> · passage {citation.chunk_index + 1}</span>
                    <p className="mt-1">{citation.excerpt}</p>
                  </li>
                ))}
              </ul>
            </details>
          </div>
        ) : null}
      </form>
    </section>
  );
}

function sourceNames(citations: { filename: string }[]) {
  return [...new Set(citations.map((citation) => citation.filename))].join(", ");
}

function AnswerText({ text }: { text: string }) {
  const paragraphs = text
    .split(/\n+/)
    .map((line) => line.replace(/^\s*[*•-]\s+/, "").trim())
    .filter(Boolean);
  return paragraphs.map((paragraph, index) => (
    <p key={index} className="mt-3 first:mt-0">
      {paragraph.split(/(\*\*[^*]+\*\*)/g).map((piece, pieceIndex) =>
        piece.startsWith("**") && piece.endsWith("**") ? (
          <strong key={pieceIndex}>{piece.slice(2, -2)}</strong>
        ) : (
          <span key={pieceIndex}>{piece}</span>
        ),
      )}
    </p>
  ));
}
