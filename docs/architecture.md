# Architecture notes

Phase 2 implements the foundation of the plan. Later phases should follow these boundaries.

## Runtime

The browser uses Next.js for the interface. Business data goes through FastAPI. Supabase Auth is the session provider in development and production, so both computers share the same accounts. A local password mode exists only for the disposable test database.

`AUTH_MODE=supabase` verifies access tokens with the project JWT secret (HS256) or the project JWKS endpoint. The first valid request creates a `profiles` row. Organization roles still live in `organization_members`, not in the client.

## Data

Every business table has `organization_id`. Repositories and services take that id from a membership check, not from an unchecked client field. The dashboard is a set of aggregate queries on that id.

Embeddings will be stored in Supabase pgvector, in `vector(384)` columns. No embedding model is loaded in this phase. Original files go to Supabase Storage under `organization_id/document_id/filename`. The API does not keep them on local disk.

The initial migration also creates `jobs`, `workflow_execution_steps`, and `outbox_messages`. HTTP handlers may insert a job. A separate process, `python -m app.workers`, claims due rows. The API process does not run that loop. Redis and Celery stay out until a later phase has work that needs a broker.

## AI boundary, not built yet

The provider manager will sit behind one interface with separate capability flags for structured output, tools, streaming, and context size. Retryable failures are timeouts, 429s, and 5xx responses. Invalid requests are not retried. Embeddings stay local.

The knowledge assistant may cite only chunk ids returned by retrieval. The analyst may execute only a validated plan object. Workflow side effects stop at a human approval and the outbox.

## Free-tier constraints already reflected

- Render's free web service has 512 MB of RAM and sleeps after 15 idle minutes. The job runner will be in-process, so schedules are best-effort there.
- Supabase's free direct database host is IPv6. The deployed API should use the shared pooler in session mode.
- The UI does not show accuracy or cost figures that were not computed from stored rows.
