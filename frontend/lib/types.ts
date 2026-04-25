// ── User & Auth ──
export interface User {
  id: string;
  email: string;
  name: string;
  colegiado_number?: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  user_id: string;
  email: string;
}

// ── Projects (stored as conversations on the backend) ──
export interface CatastroData {
  success: boolean;
  ref_catastral?: string;
  num_units?: number;
  direccion_normalizada?: string;
  codigo_postal?: string;
  provincia?: string;
  municipio?: string;
  sede_url?: string;
  error?: string | null;
}

export interface Conversation {
  id: string;
  title: string;
  pinned: boolean;
  created_at: string;
  address?: string;
  municipio?: string;
  building_type?: string;
  main_materials?: string[];
  estimated_budget?: number;
  ordenanza?: string;
  catastro_data?: CatastroData | null;
  messages?: Message[];
}

// ── Attachments ──
export interface Attachment {
  id: string;
  kind: "input" | "generated";
  filename: string;
  mime_type: string;
  size_bytes: number;
}

// ── Messages ──
export interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  attachments?: Attachment[];
  created_at?: string;
}

export interface Source {
  content: string;
  source: string;
  subject: string;
  level: string;
  similarity: number;
}

// ── API Requests ──
export interface ChatRequest {
  message: string;
  conversation_id?: string;
  files?: File[];
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  sources: Source[];
  attachments: Attachment[];
  // Subset of { "catastro" | "pgou" | "cte" | "bcca" } — which source
  // indicators the UI should light up for this turn.
  tools_used?: string[];
}

// ── Streaming events (SSE from /chat/ with stream=true) ─────────
export type ChatStreamEvent =
  | { type: "text_delta"; text: string }
  | { type: "tool_call"; name: string }
  | ChatStreamDoneEvent
  | { type: "error"; message: string };

export interface ChatStreamDoneEvent {
  type: "done";
  conversation_id: string;
  response: string;
  sources: Source[];
  attachments: Attachment[];
  tools_used?: string[];
}

export interface CreateProjectRequest {
  title?: string;
  address: string;
  municipio: string;
  ref_catastral: string;
  building_type?: string;
  main_materials: string[];
  estimated_budget?: number;
  ordenanza?: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name: string;
  colegiado_number?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}
