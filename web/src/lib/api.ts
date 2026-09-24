// Typed client for the Canopy API. Types come from the API's OpenAPI schema
// (npm run gen:api), so a response-shape change on the server breaks the build
// here instead of breaking a screen at runtime.

import type { components } from "./api-types";

export type S = components["schemas"];
export type Me = S["MeOut"];
export type Entity = S["EntityOut"];
export type GroupAccount = S["GroupAccountOut"];
export type MappingRow = S["MappingRow"];
export type GapMatrix = S["GapMatrix"];
export type Member = S["MemberOut"];
export type Invitation = S["InvitationOut"];
export type AuditEvent = S["AuditEventOut"];

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

// The session's CSRF token, echoed on every mutating request.
let csrfToken = "";
export function setCsrfToken(token: string) {
  csrfToken = token;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "include", // session cookie
    headers: {
      ...(method !== "GET" ? { "X-CSRF-Token": csrfToken } : {}),
      ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {}),
    },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (!res.ok) {
    let code = "http_error";
    let message = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      code = data?.error?.code ?? code;
      message = data?.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const ws = (id: string) => `/workspaces/${id}`;

// Browser navigations (full-page redirects through Xero).
export const loginUrl = (redirectTo = "/") => `${API_BASE}/auth/login?redirect_to=${encodeURIComponent(redirectTo)}`;
export const connectUrl = (workspaceId: string) => `${API_BASE}${ws(workspaceId)}/xero/connect`;
export const exportUrl = (workspaceId: string) => `${API_BASE}${ws(workspaceId)}/export.csv`;

export const api = {
  me: () => request<Me>("GET", "/me"),
  logout: () => request<void>("POST", "/auth/logout"),
  createWorkspace: (name: string) => request<S["IdOut"]>("POST", "/workspaces", { name }),
  acceptInvitation: (token: string) => request<S["WorkspaceIdOut"]>("POST", "/invitations/accept", { token }),

  entities: (w: string) => request<Entity[]>("GET", `${ws(w)}/entities`),
  syncEntity: (w: string, e: string, full = false) =>
    request<S["QueuedOut"]>("POST", `${ws(w)}/entities/${e}/sync?full=${full}`),

  standard: (w: string) => request<GroupAccount[]>("GET", `${ws(w)}/standard`),
  seedStandard: (w: string, entityId: string) =>
    request<S["CountOut"]>("POST", `${ws(w)}/standard/seed`, { entity_id: entityId }),
  importStandard: (w: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<S["CountOut"]>("POST", `${ws(w)}/standard/import`, form);
  },
  addGroupAccount: (w: string, body: S["NewGroupAccount"]) =>
    request<GroupAccount>("POST", `${ws(w)}/standard/accounts`, body),
  editGroupAccount: (w: string, id: string, body: S["GroupAccountChange"]) =>
    request<GroupAccount>("PATCH", `${ws(w)}/standard/accounts/${id}`, body),

  mappings: (w: string, e: string) => request<MappingRow[]>("GET", `${ws(w)}/entities/${e}/mappings`),
  resuggest: (w: string, e: string) => request<S["QueuedOut"]>("POST", `${ws(w)}/entities/${e}/mappings/suggest`),
  confirmExact: (w: string, e: string) =>
    request<S["ConfirmedOut"]>("POST", `${ws(w)}/entities/${e}/mappings/confirm-exact`),
  decide: (w: string, mappingId: string, body: S["Decision"]) =>
    request<S["DecisionOut"]>("POST", `${ws(w)}/mappings/${mappingId}/decision`, body),

  gaps: (w: string) => request<GapMatrix>("GET", `${ws(w)}/gaps`),

  members: (w: string) => request<Member[]>("GET", `${ws(w)}/members`),
  changeRole: (w: string, membershipId: string, role: string) =>
    request<S["RoleOut"]>("PATCH", `${ws(w)}/members/${membershipId}`, { role }),
  removeMember: (w: string, membershipId: string) => request<void>("DELETE", `${ws(w)}/members/${membershipId}`),
  invitations: (w: string) => request<Invitation[]>("GET", `${ws(w)}/invitations`),
  invite: (w: string, email: string, role: string) =>
    request<S["InvitationCreated"]>("POST", `${ws(w)}/invitations`, { email, role }),
  revokeInvitation: (w: string, id: string) => request<void>("DELETE", `${ws(w)}/invitations/${id}`),

  audit: (w: string) => request<AuditEvent[]>("GET", `${ws(w)}/audit`),
};
