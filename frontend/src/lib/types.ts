export type User = {
  id: string;
  email: string;
  full_name: string;
  is_super_admin: boolean;
  email_verified: boolean;
};

export type Organization = {
  id: string;
  name: string;
  slug: string;
  role: "org_admin" | "manager" | "member";
  created_at: string;
};

export type Member = {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: Organization["role"];
  created_at: string;
};

export type Dashboard = {
  documents: number;
  conversations: number;
  queries: number;
  workflows: number;
  successful_executions: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string;
  document_status: {
    pending: number;
    processing: number;
    ready: number;
    failed: number;
  };
  recent_activity: { action: string; resource_type: string; created_at: string }[];
  recent_conversations: { id: string; title: string; created_at: string }[];
};

export type AiProvider = {
  provider: string;
  model: string;
  configured: boolean;
  status: string;
  detail: string;
  models: string[];
  active: boolean;
};

export type AiProviders = {
  active_provider: string;
  fallback_providers: string[];
  providers: AiProvider[];
};

export type AiUsage = {
  requests_succeeded: number;
  requests_failed: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string;
  cost_is_estimate: boolean;
  providers: {
    provider: string;
    requests_succeeded: number;
    requests_failed: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: string;
  }[];
};

export type AiFallback = {
  provider: string;
  model: string;
  status: string;
  error_category: string | null;
  fallback_from: string | null;
  latency_ms: number | null;
  created_at: string;
};

export type AiTestResult = {
  text: string;
  provider: string;
  model: string;
  fallback_from: string | null;
  input_tokens: number;
  output_tokens: number;
  tokens_source: string;
  estimated_cost_usd: string;
  cost_is_estimate: boolean;
};

export type KnowledgeDocument = {
  id: string;
  filename: string;
  status: "pending" | "processing" | "ready" | "failed";
  size_bytes: number;
  error_message: string | null;
  created_at: string;
};

export type KnowledgeCitation = {
  document_id: string;
  filename: string;
  chunk_index: number;
  excerpt: string;
};

export type KnowledgeMode = {
  mode: "full" | "demo";
  demo: boolean;
  notice: string;
};

export type KnowledgeAnswer = {
  answer: string;
  provider: string;
  model: string;
  retrieval: "vector" | "text";
  citations: KnowledgeCitation[];
};

export type DatasetColumn = {
  name: string;
  type: string;
  missing: number;
  unique: number;
  numeric: { count: number; min: number; max: number; mean: number; sum: number } | null;
  date_min: string | null;
  date_max: string | null;
};

export type DatasetProfile = {
  columns: DatasetColumn[];
  duplicate_rows: number;
  preview: Record<string, string | number | boolean | null>[];
};

export type AnalystDataset = {
  id: string;
  name: string;
  status: "pending" | "processing" | "ready" | "failed";
  row_count: number;
  column_count: number;
  error_message: string | null;
  profile: DatasetProfile;
  created_at: string;
};

export type AnalystChart = {
  type: "bar" | "line" | "pie" | "area" | "table" | "kpi";
  data: { label: string; value: number }[];
};

export type AnalystResult = {
  id: string;
  dataset_id: string;
  question: string;
  status: "pending" | "running" | "succeeded" | "failed";
  error_message: string | null;
  calculated: { value: number | null; rows: { label: string; value: number }[]; chart: string } | null;
  facts: string[];
  interpretation: string | null;
  insights: string[];
  chart: AnalystChart | null;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  user: User;
};
