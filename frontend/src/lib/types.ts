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

export type TokenResponse = {
  access_token: string;
  token_type: string;
  user: User;
};
