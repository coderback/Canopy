// Typed client for the Canopy FastAPI backend. Shapes mirror
// backend/app/serializers.py (run_dict / proposal_dict) and the routers.

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

export type ChangeType = "item" | "account" | "contact" | "tracking";

export type WriteResult = {
  attempt: number;
  success: boolean;
  error: string | null;
  xero_id: string | null;
  created_at: string;
};

export type Proposal = {
  id: number;
  entity_id: number;
  entity_name: string | null;
  action: string;
  mapped_payload: Record<string, unknown>;
  edited_payload: Record<string, unknown> | null;
  confidence: number;
  reasoning: string;
  needs_human: boolean;
  status: string; // proposed | approved | excluded | executed | failed
  results: WriteResult[];
};

export type IngestIntent = {
  site?: string | null;
  description: string;
  amount?: number | null;
  direction?: string;
  needs_review?: boolean;
  review_reason?: string | null;
};

// For ingest runs the backend stores the file + what the AI inferred here.
export type IngestSource = {
  filename?: string;
  doc_type?: string;
  human_description?: string;
  intents?: IngestIntent[];
  caveats?: string[];
};

export type Run = {
  id: number;
  kind: string; // propagation | ingest
  change_type: string | null;
  status: string; // proposed | approved | executing | completed | partial | failed
  source_payload: Record<string, unknown> & IngestSource;
  created_at: string;
  approved_at: string | null;
  completed_at: string | null;
  proposals?: Proposal[];
};

export type EntityHealth = {
  snapshots: Record<string, { count: number; fetched_at: string }>;
  kinds_cached: number;
  kinds_total: number;
  drift: { code: string; name: string; present_in: number; of: number }[];
  drift_total: number;
};

export type Entity = {
  id: number;
  tenant_id: string;
  name: string;
  connected_at: string | null;
  snapshot_age: string | null;
  health: EntityHealth;
};

export type RowDecision = {
  proposal_id: number;
  approved: boolean;
  edited_payload?: Record<string, unknown> | null;
};

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the Canopy backend at ${API_BASE}. Is it running?`);
  }
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep default */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const getEntities = () => request<Entity[]>("/entities");
export const getRuns = () => request<Run[]>("/runs");
export const getRun = (id: number) => request<Run>(`/runs/${id}`);

export const createChange = (body: {
  change_type: ChangeType;
  payload: Record<string, unknown>;
  target_entity_ids: number[];
}) => request<Run>("/changes", { method: "POST", body: JSON.stringify(body) });

export const approveRun = (id: number, decisions: RowDecision[]) =>
  request<Run>(`/runs/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ decisions }),
  });

// Multipart upload — must NOT set Content-Type by hand; the browser adds the
// multipart boundary. So this bypasses `request` (which forces application/json).
export async function ingestFile(file: File, targetEntityIds: number[]): Promise<Run> {
  const form = new FormData();
  form.append("file", file);
  form.append("target_entity_ids", JSON.stringify(targetEntityIds));
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/ingest`, { method: "POST", body: form });
  } catch {
    throw new ApiError(0, `Cannot reach the Canopy backend at ${API_BASE}. Is it running?`);
  }
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep default */
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as Run;
}

export const seedDemo = () => request<Run>("/demo/seed", { method: "POST" });
export const seedDemoIngest = () => request<Run>("/demo/seed-ingest", { method: "POST" });

export { ApiError };
