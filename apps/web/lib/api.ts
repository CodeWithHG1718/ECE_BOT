import type {
  ChatMessage,
  Conversation,
  HealthStatus,
  ProfileOptions,
  SessionCredentials,
  StudyProfile,
} from "./types";

const API_BASE = (
  process.env.NEXT_PUBLIC_SIGNAL_API_BASE_URL || ""
).replace(/\/+$/, "");
const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("X-Session-Token", token);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${API_PREFIX}${path}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: init.signal ?? AbortSignal.timeout(25_000),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError("The request took too long. Check your connection and try again.", 408, "timeout");
    }
    throw new ApiError("Signal could not reach the service. Check that the local API is running, then try again.", 0, "unavailable");
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const envelope = payload as {
      error?: { message?: string; code?: string };
      detail?: string;
    } | null;
    const message = envelope?.error?.message || envelope?.detail;
    throw new ApiError(
      message || `The service returned an error (${response.status}). Try again in a moment.`,
      response.status,
      envelope?.error?.code,
    );
  }

  return payload as T;
}

function sessionPath(sessionId: string) {
  return `/sessions/${encodeURIComponent(sessionId)}`;
}

export const api = {
  health: () => request<HealthStatus>("/health"),
  profileOptions: (year?: string, semester?: string) => request<ProfileOptions>(
    `/profile-options${year ? `?study_year=${encodeURIComponent(year)}${semester ? `&semester=${encodeURIComponent(semester)}` : ""}` : ""}`),
  createSession: () => request<SessionCredentials & { profile: null }>("/sessions", { method: "POST" }),
  getProfile: (session: SessionCredentials) =>
    request<{ profile: StudyProfile | null }>(`${sessionPath(session.session_id)}/profile`, {}, session.session_token),
  saveProfile: (session: SessionCredentials, profile: StudyProfile) =>
    request<{ profile: StudyProfile & { session_id: string } }>(
      `${sessionPath(session.session_id)}/profile`,
      { method: "PUT", body: JSON.stringify(profile) },
      session.session_token,
    ),
  listConversations: (session: SessionCredentials) =>
    request<{ conversations: Conversation[] }>(
      `${sessionPath(session.session_id)}/conversations`,
      {},
      session.session_token,
    ),
  createConversation: (session: SessionCredentials) =>
    request<{ conversation_id: string }>(
      `${sessionPath(session.session_id)}/conversations`,
      { method: "POST" },
      session.session_token,
    ),
  messages: (session: SessionCredentials, conversationId: string) =>
    request<{ messages: ChatMessage[] }>(
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
      {},
      session.session_token,
    ),
  sendMessage: (session: SessionCredentials, conversationId: string, text: string) =>
    request<{ user_message: ChatMessage; assistant_message: ChatMessage }>(
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
      { method: "POST", body: JSON.stringify({ text }) },
      session.session_token,
    ),
};

export function readStoredSession(): SessionCredentials | null {
  try {
    const value = localStorage.getItem("signal.session.v1") || sessionStorage.getItem("signal.session.v1");
    if (!value) return null;
    const parsed = JSON.parse(value) as Partial<SessionCredentials>;
    if (typeof parsed.session_id !== "string" || typeof parsed.session_token !== "string") return null;
    const credentials = { session_id: parsed.session_id, session_token: parsed.session_token };
    storeSession(credentials);
    return credentials;
  } catch {
    return null;
  }
}

export function storeSession(session: SessionCredentials) {
  localStorage.setItem("signal.session.v1", JSON.stringify({session_id: session.session_id, session_token: session.session_token}));
}

export function clearStoredSession() {
  sessionStorage.removeItem("signal.session.v1");
  localStorage.removeItem("signal.session.v1");
}
