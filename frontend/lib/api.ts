import {
  AuthResponse,
  RegisterRequest,
  LoginRequest,
  Conversation,
  ChatRequest,
  ChatResponse,
  ChatStreamEvent,
  ChatStreamDoneEvent,
  CreateProjectRequest,
  User,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const TOKEN_KEY = "token";
const REFRESH_KEY = "refresh_token";

class ApiClient {
  private token: string | null = null;
  private refreshToken: string | null = null;

  // A single in-flight refresh so multiple parallel 401s don't stampede
  // `/auth/refresh`. They all await the same promise.
  private refreshInFlight: Promise<string | null> | null = null;

  // ── Token storage ────────────────────────────────────────────
  setTokens(access: string, refresh: string) {
    this.token = access;
    this.refreshToken = refresh;
    if (typeof window !== "undefined") {
      localStorage.setItem(TOKEN_KEY, access);
      localStorage.setItem(REFRESH_KEY, refresh);
    }
  }

  // Legacy single-token setter for callers that only know the access
  // token — shouldn't be used by auth flows but kept for safety.
  setToken(token: string) {
    this.token = token;
    if (typeof window !== "undefined") {
      localStorage.setItem(TOKEN_KEY, token);
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== "undefined") {
      this.token = localStorage.getItem(TOKEN_KEY);
    }
    return this.token;
  }

  getRefreshToken(): string | null {
    if (this.refreshToken) return this.refreshToken;
    if (typeof window !== "undefined") {
      this.refreshToken = localStorage.getItem(REFRESH_KEY);
    }
    return this.refreshToken;
  }

  clearToken() {
    this.token = null;
    this.refreshToken = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(REFRESH_KEY);
    }
  }

  // ── Refresh ──────────────────────────────────────────────────
  /**
   * Attempts to refresh the access token using the stored refresh
   * token. Returns the new access token, or null if refresh failed
   * (in which case callers should route the user back to /login).
   * Shared in-flight promise prevents duplicate refresh calls.
   */
  private async refresh(): Promise<string | null> {
    if (this.refreshInFlight) return this.refreshInFlight;
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return null;

    this.refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_URL}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) {
          // Refresh itself was rejected — tokens are dead.
          this.clearToken();
          return null;
        }
        const data = (await res.json()) as AuthResponse;
        this.setTokens(data.access_token, data.refresh_token);
        return data.access_token;
      } catch {
        this.clearToken();
        return null;
      } finally {
        this.refreshInFlight = null;
      }
    })();

    return this.refreshInFlight;
  }

  /**
   * Central fetch wrapper that:
   *   1. Attaches the current access token as a Bearer header
   *   2. On a 401 response, tries to refresh once, then retries
   *   3. If refresh fails, returns the 401 to the caller
   *
   * Works for both JSON and FormData bodies. Never sets Content-Type
   * when `body` is FormData (the browser adds the multipart boundary).
   */
  private async authedFetch(
    path: string,
    init: RequestInit = {}
  ): Promise<Response> {
    const buildInit = (token: string | null): RequestInit => {
      const headers = new Headers(init.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);
      // Only set JSON Content-Type when there is a body and it isn't
      // FormData (which needs a multipart boundary we don't control).
      if (
        init.body &&
        !(init.body instanceof FormData) &&
        !headers.has("Content-Type")
      ) {
        headers.set("Content-Type", "application/json");
      }
      return { ...init, headers };
    };

    let res = await fetch(`${API_URL}${path}`, buildInit(this.getToken()));

    if (res.status === 401) {
      const newToken = await this.refresh();
      if (newToken) {
        res = await fetch(`${API_URL}${path}`, buildInit(newToken));
      }
    }

    return res;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const res = await this.authedFetch(path, options);
    if (!res.ok) {
      const error = await res
        .json()
        .catch(() => ({ detail: "Request failed" }));
      throw new Error(error.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  // ── Auth ──
  async register(data: RegisterRequest): Promise<AuthResponse> {
    // Register and login skip the bearer header since there is none yet,
    // but still benefit from the shared request helper.
    const res = await fetch(`${API_URL}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Register failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const body = (await res.json()) as AuthResponse;
    this.setTokens(body.access_token, body.refresh_token);
    return body;
  }

  async login(data: LoginRequest): Promise<AuthResponse> {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Login failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const body = (await res.json()) as AuthResponse;
    this.setTokens(body.access_token, body.refresh_token);
    return body;
  }

  async getProfile(): Promise<User> {
    return this.request<User>("/auth/profile");
  }

  async deleteAccount(): Promise<void> {
    await this.request("/auth/account", { method: "DELETE" });
    this.clearToken();
  }

  logout() {
    this.clearToken();
  }

  // ── Conversations ──
  async getConversations(): Promise<Conversation[]> {
    return this.request<Conversation[]>("/conversations/");
  }

  async getConversation(id: string): Promise<Conversation> {
    return this.request<Conversation>(`/conversations/${id}`);
  }

  async createProject(data: CreateProjectRequest): Promise<Conversation> {
    return this.request<Conversation>("/conversations/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateProject(
    id: string,
    updates: Partial<{
      title: string;
      pinned: boolean;
      address: string;
      municipio: string;
      building_type: string;
      main_materials: string[];
      estimated_budget: number;
      ordenanza: string;
    }>
  ): Promise<Conversation> {
    return this.request<Conversation>(`/conversations/${id}`, {
      method: "PUT",
      body: JSON.stringify(updates),
    });
  }

  async deleteConversation(id: string): Promise<void> {
    await this.request(`/conversations/${id}`, { method: "DELETE" });
  }

  // ── Catastro ──
  async fetchCatastroData(projectId: string): Promise<any> {
    return this.request(`/catastro/lookup-and-save/${projectId}`, {
      method: "POST",
    });
  }

  // ── Chat ──
  async sendMessage(
    data: ChatRequest,
    signal?: AbortSignal,
  ): Promise<ChatResponse> {
    const form = new FormData();
    form.append("message", data.message);
    if (data.conversation_id) {
      form.append("conversation_id", data.conversation_id);
    }
    for (const f of data.files || []) {
      form.append("files", f, f.name);
    }

    const res = await this.authedFetch("/chat/", {
      method: "POST",
      body: form,
      signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  /**
   * Streaming variant of sendMessage. Parses the server's SSE stream
   * and fires onEvent() for every frame. Events arrive in this order:
   *
   *   {type:"text_delta",  text:"..."}      — incremental model tokens
   *   {type:"tool_call",   name:"..."}      — Claude started a tool
   *   {type:"done",        response, sources, tools_used, attachments,
   *                         conversation_id}
   *   {type:"error",       message}
   *
   * Resolves with the final `done` event once the stream finishes.
   */
  async sendMessageStream(
    data: ChatRequest,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<ChatStreamDoneEvent> {
    const form = new FormData();
    form.append("message", data.message);
    form.append("stream", "true");
    if (data.conversation_id) {
      form.append("conversation_id", data.conversation_id);
    }
    for (const f of data.files || []) {
      form.append("files", f, f.name);
    }

    const res = await this.authedFetch("/chat/", {
      method: "POST",
      body: form,
      signal,
      // Force bypass of any stale Service Worker cache for the streaming
      // endpoint — some browsers silently buffer SSE otherwise.
      headers: { Accept: "text/event-stream" },
    });
    if (!res.ok || !res.body) {
      const err = await res.json?.().catch?.(() => ({ detail: "Stream failed" }));
      throw new Error((err && err.detail) || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let doneEvent: ChatStreamDoneEvent | null = null;

    // Parse each SSE frame (separated by blank lines, one `data:` line each).
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Split on blank line (end of SSE frame). Keep the trailing
        // partial frame in the buffer for the next read.
        let frameEnd: number;
        while ((frameEnd = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, frameEnd);
          buffer = buffer.slice(frameEnd + 2);
          // One or more "data: <json>" lines per frame. Backend
          // emits one data line per event so this is straightforward.
          const line = frame.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          const payload = line.slice(5).trim();
          if (!payload) continue;
          let parsed: ChatStreamEvent;
          try {
            parsed = JSON.parse(payload) as ChatStreamEvent;
          } catch {
            continue; // malformed frame — skip
          }
          onEvent(parsed);
          if (parsed.type === "done") {
            doneEvent = parsed;
          } else if (parsed.type === "error") {
            throw new Error(parsed.message || "Stream error");
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    if (!doneEvent) {
      throw new Error("Stream ended before 'done' event");
    }
    return doneEvent;
  }

  // ── Attachments ──
  /**
   * Downloads an attachment via the auth-protected route, through
   * the same refresh-aware fetch wrapper so a stale token doesn't
   * break the download mid-conversation.
   */
  async downloadAttachment(
    attachmentId: string,
    filename: string
  ): Promise<void> {
    const res = await this.authedFetch(`/attachments/${attachmentId}`, {});
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Download failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
}

export const api = new ApiClient();
