# AI providers

Gemini is the primary chat provider. Groq is the fallback. Ollama is optional and only used when a local server is running. API keys stay in `backend/.env` on each computer. They are not stored in the database and are not returned to the browser.

The existing `document_chunks.embedding` column is `vector(384)`. Embeddings use the ONNX build of `sentence-transformers/all-MiniLM-L6-v2`, which has that same width. PyTorch is not installed. Do not change the dimension without a new migration.

## Configure Gemini

1. Create a key in Google AI Studio.
2. Set `GEMINI_API_KEY` in `backend/.env`.
3. Restart the API.

`GEMINI_MODEL` defaults to `gemini-flash-lite-latest`. Google has closed `gemini-2.5-flash-lite` to new accounts.

## Configure Groq

1. Create a key in the Groq console.
2. Set `GROQ_API_KEY` in `backend/.env`.
3. Restart the API.

`GROQ_MODEL` defaults to `openai/gpt-oss-20b`. `AI_FALLBACK_PROVIDERS=groq,ollama` tells the API to try Groq after Gemini returns a recoverable error such as HTTP 429.

## What the admin page shows

Open **AI providers** as an organization admin.

- Provider status comes from a live model-list call. A missing key is `not_configured`. A refused connection is `unavailable`.
- Request, token, and cost totals are sums from this organization's `ai_usage_logs` rows. An empty table shows zeros.
- Costs use published list prices and are marked as estimates. They are not invoices.
- Token counts that the provider returns are marked `provider`. Counts guessed from text length are marked `estimated`.

A test prompt is stored only as usage metadata. The prompt text is not written to the usage log.

## Knowledge

Organization members upload a `.txt`, `.md`, `.csv`, `.docx`, or text PDF on the Knowledge page. The file is stored in the private `documents` bucket and split into passages. Each passage is embedded with the 384-dimension model above. A question is answered only from the matching passages, and the page shows those passages as citations.

The first upload downloads the embedding model onto that computer. Later uploads reuse it.

## Apply the usage migration

From `backend`, against the shared Supabase project:

```powershell
.\.venv\Scripts\python -m alembic upgrade head
```

This adds columns to `ai_usage_logs`. It does not drop or recreate tables.
