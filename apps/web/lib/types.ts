export interface SessionCredentials {
  session_id: string;
  session_token: string;
}

export interface StudyProfile {
  study_year: number;
  section: string;
  academic_cohort: string | null;
  semester: number | null;
}

export interface ProfileOptions {
  study_years: Array<{ value: number; label: string }>;
  sections_by_year: Record<string, string[]>;
  academic_sessions: Array<{ value: string; label: string }>;
}

export interface HealthStatus {
  status: string;
  dependencies: {
    database: string;
    chat_model: string;
    embeddings: string;
  };
}

export interface Conversation {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export type Presentation =
  | "answer"
  | "course_list"
  | "timetable"
  | "exam_schedule"
  | "resources"
  | "faculty"
  | "projects";

export interface SourceCitation {
  title?: string | null;
  url?: string | null;
  page?: string | number | null;
  status?: string | null;
  verification_status?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  presentation?: Presentation;
  data?: unknown;
  sources?: SourceCitation[];
  warnings?: string[];
  created_at?: string;
}
