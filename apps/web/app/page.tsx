"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, clearStoredSession, readStoredSession, storeSession } from "@/lib/api";
import type {
  ChatMessage,
  Conversation,
  HealthStatus,
  Presentation,
  ProfileOptions,
  SessionCredentials,
  SourceCitation,
  StudyProfile,
} from "@/lib/types";

type Screen = "landing" | "setup" | "workspace";
type IconName = "plus" | "message" | "send" | "arrow" | "close" | "chevron" | "copy" | "check" | "menu" | "book" | "calendar" | "clock" | "library" | "users" | "spark" | "external" | "retry";

const quickPrompts = [
  { label: "Courses in my year", text: "What courses are in my study year?", icon: "book" as const },
  { label: "My timetable", text: "Show my timetable", icon: "calendar" as const },
  { label: "Syllabus topics", text: "What syllabus topics are available for ECC-201?", icon: "book" as const },
  { label: "Exam details", text: "What exam information is available?", icon: "clock" as const },
  { label: "Study resources", text: "Find study resources for my courses", icon: "library" as const },
  { label: "Faculty & projects", text: "What faculty research and projects are recorded?", icon: "users" as const },
];

const presentationNames: Record<Presentation, string> = {
  answer: "Answer",
  course_list: "Course record",
  timetable: "Timetable records",
  exam_schedule: "Exam schedule",
  resources: "Resource matches",
  faculty: "Faculty records",
  projects: "Project records",
};

const fieldNames: Record<string, string> = {
  course_code: "Course",
  course_title: "Title",
  code: "Course",
  title: "Title",
  day: "Day",
  start_time: "Starts",
  end_time: "Ends",
  exam_date: "Date",
  date_text: "Date",
  date_ranges: "Date range",
  dates: "Dates",
  slot: "Slot",
  room: "Room",
  faculty: "Faculty",
  session_type: "Class type",
  course_batch: "Course batch",
  student_sections: "Sections",
  applicability: "Applicability",
  timezone: "Time zone",
  source_status: "Source status",
  programme_scope: "Program scope",
  event_type: "Event type",
  exam_type: "Exam type",
  year: "Year",
  semester: "Semester",
  term: "Term",
  credits: "Credits",
  ordinal: "Section",
  text: "Source passage",
  name: "Name",
  department: "Department",
  research_interests: "Research interests",
  description: "Description",
  project_title: "Project",
  "fields.Scheme/Title": "Project",
  "fields.Faculty": "Faculty",
  "fields.Year": "Year",
  "fields.Funding Agency": "Funding agency",
  designation: "Designation",
  research_interests_directory: "Research interests",
  "sections.Research Interests": "Research interests",
  profile_extraction_status: "Profile status",
  supervision_availability: "Supervision availability",
};

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    plus: <><path d="M12 5v14M5 12h14" /></>,
    message: <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5 8 8 0 0 1-3.5-.8L4 20l1.2-4.1A7.5 7.5 0 1 1 20 11.5Z" /></>,
    send: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    close: <><path d="m18 6-12 12M6 6l12 12" /></>,
    chevron: <><path d="m6 9 6 6 6-6" /></>,
    copy: <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    menu: <><path d="M4 6h16M4 12h16M4 18h16" /></>,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22Z" /><path d="M4 5.5v14A2.5 2.5 0 0 1 6.5 17H20M8 7h8" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    library: <><path d="M4 19V5M9 19V5M14 19V5M19 19V5M2 19h20M2 5h20" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM20 8v6M23 11h-6" /></>,
    spark: <><path d="m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-2-5.8L4 11l6-2.2L12 3Z" /><path d="m19 15 .9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z" /></>,
    external: <><path d="M14 3h7v7M10 14 21 3" /><path d="M19 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h6" /></>,
    retry: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M5.5 9A7 7 0 0 1 17 5l3 2M4 17l3 2a7 7 0 0 0 11.5-4" /></>,
  };
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {paths[name]}
    </svg>
  );
}
function SignalMark({ large = false }: { large?: boolean }) {
  return (
    <span className={`signal-mark${large ? " signal-mark-large" : ""}`} aria-hidden="true">
      <svg viewBox="0 0 38 38" fill="none">
        <path d="M3 20h7l3.2-9 6.3 18 4.2-12 2.2 3H35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

function Waveform() {
  return (
    <div className="wave-art" aria-hidden="true">
      <div className="wave-art-top"><span>FIELD NOTE / 01</span><span>ECE · IITR</span></div>
      <svg className="wave-drawing" viewBox="0 0 660 330" fill="none" preserveAspectRatio="xMidYMid meet">
        <path className="wave-grid" d="M0 55H660M0 110H660M0 165H660M0 220H660M0 275H660M55 0V330M110 0V330M165 0V330M220 0V330M275 0V330M330 0V330M385 0V330M440 0V330M495 0V330M550 0V330M605 0V330" />
        <path className="wave-axis" d="M0 165H660" />
        <path className="wave-line wave-line-soft" d="M0 165h90l20-2 14-3 16-11 14-17 10-9 9 21 16 51 11 28 10-8 15-52 10-39 12-5 10 19 14 27 13 9 13-10 12-22 9-12 10 3 16 23 12 10 18-4 15-17 10-13 12 3 13 21 14 12h66" />
        <path className="wave-line" d="M0 165h90l20-2 14-3 16-11 14-17 10-9 9 21 16 51 11 28 10-8 15-52 10-39 12-5 10 19 14 27 13 9 13-10 12-22 9-12 10 3 16 23 12 10 18-4 15-17 10-13 12 3 13 21 14 12h66" />
        <circle className="wave-point" cx="168" cy="132" r="4"/><circle className="wave-point" cx="245" cy="222" r="4"/><circle className="wave-point" cx="404" cy="161" r="4"/>
        <path className="wave-tick" d="M168 120v-30M245 235v29M404 148v-32" />
        <path className="wave-label-line" d="M168 90h57M245 264h72M404 116h58" />
      </svg>
      <div className="wave-art-bottom"><span>01 — ACADEMIC RECORDS</span><span>02 — OPEN QUESTIONS</span><span>↗ SOURCE FIRST</span></div>
    </div>
  );
}

function displayDate(date?: string) {
  if (!date) return "";
  const value = new Date(date);
  if (Number.isNaN(value.getTime())) return "";
  return value.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function humanize(value: string) {
  return fieldNames[value] || value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(formatValue).join(", ");
  return "See source details";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const hiddenRecordFields = [
  "evidence", "metadata", "score", "content_mapping", "course_id", "syllabus_source_codes",
  "faculty_id", "project_id", "profile_url", "url", "official_contact_fields", "raw_cells", "fields", "sections",
];

function visibleRecordEntries(record: Record<string, unknown>): Array<[string, unknown]> {
  const entries: Array<[string, unknown]> = [];
  for (const [key, value] of Object.entries(record)) {
    if (key === "fields" && isRecord(value)) {
      for (const [field, fieldValue] of Object.entries(value)) {
        if (fieldValue === null || fieldValue === undefined || fieldValue === "") continue;
        if (typeof fieldValue !== "object") entries.push([`fields.${field}`, fieldValue]);
      }
      continue;
    }
    if (key === "sections" && Array.isArray(value)) {
      for (const section of value) {
        if (isRecord(section) && typeof section.heading === "string" && typeof section.text === "string" && section.text) {
          entries.push([`sections.${section.heading}`, section.text]);
        }
      }
      continue;
    }
    if (hiddenRecordFields.includes(key)) continue;
    if (value === null || value === undefined || value === "") continue;
    if (typeof value !== "object" || (Array.isArray(value) && value.every((item) => typeof item !== "object"))) entries.push([key, value]);
  }
  return entries;
}

function recordValue(record: Record<string, unknown>, field: string) {
  if (field.startsWith("fields.")) {
    const values = record.fields;
    return isRecord(values) ? values[field.slice("fields.".length)] : undefined;
  }
  if (field.startsWith("sections.") && Array.isArray(record.sections)) {
    const heading = field.slice("sections.".length);
    const section = record.sections.find((item) => isRecord(item) && item.heading === heading);
    return isRecord(section) ? section.text : undefined;
  }
  return record[field];
}

function Records({ presentation, data }: { presentation: Presentation; data: unknown }) {
  if (data === null || data === undefined) return null;
  const records = Array.isArray(data) ? data.filter(isRecord) : isRecord(data) ? [data] : [];
  if (records.length === 0) return null;

  if (presentation === "course_list") {
    const course = records[0];
    const entries = Array.isArray(course.curriculum_entries) ? course.curriculum_entries.filter(isRecord) : [];
    const topics = Array.isArray(course.syllabus) ? course.syllabus.filter(isRecord) : [];
    return (
      <section className="structured-block" aria-label="Structured course records">
        <div className="structured-heading"><span>STRUCTURED RECORD</span><span>{presentationNames[presentation]}</span></div>
        <div className="course-record-title"><strong>{formatValue(course.code)}</strong><span>{formatValue(course.title)}</span></div>
        {entries.length > 0 && <div className="facts-table-wrap"><table className="facts-table"><thead><tr>{["year", "semester", "term", "credits", "applicability"].map((field) => <th key={field}>{humanize(field)}</th>)}</tr></thead><tbody>{entries.map((entry, index) => <tr key={index}>{["year", "semester", "term", "credits", "applicability"].map((field) => <td key={field}>{formatValue(entry[field])}</td>)}</tr>)}</tbody></table></div>}
        {topics.length > 0 && <div className="topic-list"><div className="topic-list-label">SYLLABUS SECTIONS</div>{topics.map((topic, index) => <p key={index}><span>{formatValue(topic.ordinal)}</span>{formatValue(topic.text)}</p>)}</div>}
        {!entries.length && !topics.length && <FactRows record={course} exclude={["evidence", "content_mapping", "course_id", "syllabus_source_codes"]} />}
      </section>
    );
  }

  const preferred: Partial<Record<Presentation, string[]>> = {
    timetable: ["course_code", "course_title", "day", "start_time", "end_time", "timezone", "room", "faculty", "session_type", "applicability"],
    exam_schedule: ["course_code", "exam_date", "day", "start_time", "end_time", "timezone", "slot", "room", "exam_type", "applicability"],
    answer: ["title", "date_text", "dates", "event_type", "day", "programme_scope", "source_status", "name", "department", "research_interests", "project_title", "description", "text"],
    resources: ["title", "text", "source", "resource_type", "course_code"],
    faculty: ["name", "designation", "research_interests_directory", "research_interests", "sections.Research Interests", "profile_extraction_status", "supervision_availability"],
    projects: ["fields.Scheme/Title", "project_title", "title", "fields.Faculty", "fields.Year", "fields.Funding Agency"],
  };
  const columns = (preferred[presentation] || []).filter((field) => records.some((record) => recordValue(record, field) !== undefined));
  const availableColumns = [...new Set(records.flatMap((record) => visibleRecordEntries(record).map(([field]) => field)))];
  const selectedColumns = columns.length ? columns : availableColumns.slice(0, 5);

  return (
    <section className="structured-block" aria-label={`Structured ${presentationNames[presentation].toLowerCase()}`}>
      <div className="structured-heading"><span>STRUCTURED RECORDS</span><span>{presentationNames[presentation]}{records.length > 1 ? ` · ${records.length}` : ""}</span></div>
      {selectedColumns.length > 0 ? (
        <div className="facts-table-wrap"><table className="facts-table"><thead><tr>{selectedColumns.map((field) => <th key={field}>{humanize(field)}</th>)}</tr></thead><tbody>{records.map((record, index) => <tr key={index}>{selectedColumns.map((field) => <td key={field}>{formatValue(recordValue(record, field))}</td>)}</tr>)}</tbody></table></div>
      ) : records.map((record, index) => <FactRows key={index} record={record} exclude={hiddenRecordFields} />)}
      {presentation === "resources" && records.length > 0 && records.some((record) => typeof record.text === "string") && <p className="record-note">Passages are shown as retrieved; use the cited source for context.</p>}
    </section>
  );
}

function FactRows({ record, exclude = [] }: { record: Record<string, unknown>; exclude?: string[] }) {
  const visible = visibleRecordEntries(record).filter(([key]) => !exclude.includes(key)).slice(0, 8);
  if (!visible.length) return null;
  return <dl className="fact-rows">{visible.map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{formatValue(value)}</dd></div>)}</dl>;
}

function CitationList({ sources }: { sources: SourceCitation[] }) {
  if (!sources.length) return null;
  return (
    <section className="citation-list" aria-label="Sources">
      <div className="citation-title">SOURCES <span>{String(sources.length).padStart(2, "0")}</span></div>
      <ul>{sources.map((source, index) => {
        const safeUrl = typeof source.url === "string" && /^https?:\/\//i.test(source.url) ? source.url : undefined;
        const title = source.title || "Source record";
        return <li key={`${source.url || title}-${index}`}>
          {safeUrl ? <a href={safeUrl} target="_blank" rel="noreferrer">{title}<Icon name="external" size={13} /></a> : <span className="citation-text">{title}</span>}
          <span className="citation-meta">{source.page ? `p. ${source.page} · ` : ""}{source.status || source.verification_status || "Source"}</span>
        </li>;
      })}</ul>
    </section>
  );
}

function ErrorNotice({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return <div className="error-notice" role="alert"><span className="error-symbol">!</span><p>{message}</p>{onDismiss && <button type="button" className="icon-button error-dismiss" onClick={onDismiss} aria-label="Dismiss message"><Icon name="close" size={15} /></button>}</div>;
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

function isUnauthorized(error: unknown) {
  return error instanceof ApiError && error.status === 401;
}

export default function Home() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [session, setSession] = useState<SessionCredentials | null>(null);
  const [profile, setProfile] = useState<StudyProfile | null>(null);
  const [profileOptions, setProfileOptions] = useState<ProfileOptions | null>(null);
  const [year, setYear] = useState("");
  const [section, setSection] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");
  const [mobileSidebar, setMobileSidebar] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const report = useCallback((caught: unknown) => {
    if (isUnauthorized(caught)) {
      clearStoredSession();
      setSession(null);
      setProfile(null);
      setConversations([]);
      setConversationId(null);
      setMessages([]);
      setScreen("landing");
      setError("This anonymous session has expired. Launch Signal to start a new one.");
      return;
    }
    setError(getErrorMessage(caught));
  }, []);

  useEffect(() => {
    let current = true;
    void api.health().then((result) => { if (current) setHealth(result); }).catch(() => { if (current) setHealth(null); });
    const saved = readStoredSession();
    if (!saved) return () => { current = false; };

    setBusy("restore");
    setSession(saved);
    const restore = async () => {
      try {
        const [{ profile: savedProfile }, { conversations: savedConversations }] = await Promise.all([
          api.getProfile(saved),
          api.listConversations(saved),
        ]);
        if (!current) return;
        setProfile(savedProfile);
        setConversations(savedConversations);
        if (!savedProfile) {
          setScreen("setup");
          const options = await api.profileOptions();
          if (current) setProfileOptions(options);
          return;
        }
        setScreen("workspace");
        const first = savedConversations[0];
        if (first) {
          setConversationId(first.conversation_id);
          try {
            const result = await api.messages(saved, first.conversation_id);
            if (current) setMessages(result.messages);
          } catch (caught) {
            if (current && !isUnauthorized(caught)) setHistoryError(true);
            throw caught;
          }
        }
      } catch (caught) {
        if (!current) return;
        if (isUnauthorized(caught)) {
          clearStoredSession();
          setSession(null);
          setError("This anonymous session has expired. Launch Signal to start a new one.");
          setScreen("landing");
        } else {
          setError(getErrorMessage(caught));
        }
      } finally {
        if (current) setBusy(null);
      }
    };
    void restore();
    return () => { current = false; };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "end" });
  }, [messages, busy]);

  const availableYears = profileOptions?.study_years || [];
  const availableSections = profileOptions?.sections_by_year[year] || [];

  async function launch() {
    setScreen("setup");
    setError("");
    setBusy("options");
    try {
      const options = await api.profileOptions();
      setProfileOptions(options);
      if (!session) {
        const credentials = await api.createSession();
        storeSession(credentials);
        setSession({ session_id: credentials.session_id, session_token: credentials.session_token });
      }
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function changeProfile() {
    setError("");
    setScreen("setup");
    setBusy("options");
    try {
      const options = await api.profileOptions();
      setProfileOptions(options);
      setYear(profile ? String(profile.study_year) : "");
      setSection(profile?.section || "");
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function refreshConversations(activeSession: SessionCredentials) {
    const result = await api.listConversations(activeSession);
    setConversations(result.conversations);
    return result.conversations;
  }

  async function saveAcademicProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || !year || !section) return;
    const selectedYear = availableYears.find((item) => item.value === Number(year));
    if (!selectedYear || !availableSections.includes(section)) {
      setError("Choose a year and section from the source-supported options.");
      return;
    }
    setBusy("profile");
    setError("");
    const nextProfile: StudyProfile = { study_year: Number(year), section, academic_cohort: null, semester: null };
    try {
      await api.saveProfile(session, nextProfile);
      setProfile(nextProfile);
      if (!conversationId) {
        const created = await api.createConversation(session);
        setConversationId(created.conversation_id);
        setMessages([]);
        await refreshConversations(session);
      }
      setScreen("workspace");
    } catch (caught) {
      if (isUnauthorized(caught)) report(caught);
      else {
        setError(getErrorMessage(caught));
      }
    } finally {
      setBusy(null);
    }
  }

  async function startConversation(initialPrompt?: string) {
    if (!session) return;
    setBusy("new-conversation");
    setError("");
    try {
      const created = await api.createConversation(session);
      setConversationId(created.conversation_id);
      setMessages([]);
      setDraft(initialPrompt || "");
      if (initialPrompt) {
        setBusy("send");
        const response = await api.sendMessage(session, created.conversation_id, initialPrompt);
        setMessages([response.user_message, response.assistant_message]);
        setDraft("");
      }
      try {
        await refreshConversations(session);
      } catch (caught) {
        if (isUnauthorized(caught)) report(caught);
        else setError("The conversation was created, but the list could not be refreshed. Your new conversation is ready below.");
      }
      setMobileSidebar(false);
      if (!initialPrompt) textareaRef.current?.focus();
    } catch (caught) {
      report(caught);
    } finally {
      setBusy(null);
    }
  }

  async function openConversation(item: Conversation, force = false) {
    if (!session || (!force && item.conversation_id === conversationId)) {
      setMobileSidebar(false);
      return;
    }
    setBusy(`history:${item.conversation_id}`);
    setError("");
    setHistoryError(false);
    try {
      const result = await api.messages(session, item.conversation_id);
      setConversationId(item.conversation_id);
      setMessages(result.messages);
      setMobileSidebar(false);
    } catch (caught) {
      if (isUnauthorized(caught)) report(caught);
      else {
        setHistoryError(true);
        setError(getErrorMessage(caught));
      }
    } finally {
      setBusy(null);
    }
  }

  async function sendMessage(text = draft) {
    const cleaned = text.trim();
    if (!cleaned || cleaned.length > 4000 || !session || !conversationId || busy) return;
    setBusy("send");
    setError("");
    const optimisticId = `pending-${Date.now()}`;
    if (cleaned === draft.trim()) setDraft("");
    setMessages((current) => [...current, {
      id: optimisticId,
      role: "user",
      content: cleaned,
      presentation: "answer",
      created_at: new Date().toISOString(),
    }]);
    try {
      const result = await api.sendMessage(session, conversationId, cleaned);
      setMessages((current) => [...current.filter((item) => item.id !== optimisticId), result.user_message, result.assistant_message]);
      try {
        await refreshConversations(session);
      } catch (caught) {
        if (isUnauthorized(caught)) report(caught);
        else setError("Your message was sent, but the conversation list could not be refreshed.");
      }
    } catch (caught) {
      setMessages((current) => current.filter((item) => item.id !== optimisticId));
      if (cleaned === draft.trim() || draft === "") setDraft(cleaned);
      report(caught);
    } finally {
      setBusy(null);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void sendMessage();
    }
  }

  async function copyMessage(message: ChatMessage) {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(message.id);
      window.setTimeout(() => setCopied((current) => current === message.id ? "" : current), 1500);
    } catch {
      setError("Copy is unavailable in this browser. Select the answer text to copy it.");
    }
  }

  function clearError() {
    setError("");
    setHistoryError(false);
  }

  return (
    <main className="app-root">
      {screen === "landing" && (
        <section className="landing-shell">
          <header className="landing-header">
            <a className="brand-lockup" href="#home" aria-label="Signal home"><SignalMark /><span>signal<span className="brand-period">.</span></span></a>
            <div className="landing-index"><span className="status-dot" /> STUDY DESK / IIT ROORKEE ECE</div>
          </header>
          <div className="landing-main" id="home">
            <div className="landing-copy">
              <div className="eyebrow"><span className="eyebrow-rule" /> A SOURCE-LED STUDY ASSISTANT</div>
              <h1>A clearer signal<br />for your <em>studies.</em></h1>
              <p className="landing-lede">Find your way through ECE courses, timetables, exams, and study resources. Start with your academic profile, then ask in your own words.</p>
              {error && <ErrorNotice message={error} onDismiss={clearError} />}
              <button className="button button-primary launch-button" type="button" onClick={() => void launch()} disabled={busy !== null}>
                {busy === "restore" ? "Restoring your session…" : busy === "options" ? "Connecting to Signal…" : "Launch Signal"}
                <Icon name="arrow" size={17} />
              </button>
              <div className="landing-reassurance"><span>NO INSTITUTE LOGIN</span><span className="small-separator">·</span><span>PROFILE FROM AVAILABLE RECORDS</span></div>
            </div>
            <Waveform />
          </div>
          <footer className="landing-footer"><span>Built for the questions that come up between lectures.</span><span>Independent student project · Not an official IIT Roorkee service</span></footer>
        </section>
      )}

      {screen === "setup" && (
        <section className="setup-shell">
          <header className="setup-header">
            <a className="brand-lockup" href="#home" onClick={(event) => { event.preventDefault(); setScreen("landing"); clearError(); }} aria-label="Return to Signal home"><SignalMark /><span>signal<span className="brand-period">.</span></span></a>
            <span className="step-indicator"><span>01</span> / ACADEMIC PROFILE</span>
          </header>
          <div className="setup-layout">
            <div className="setup-intro">
              <div className="eyebrow"><span className="eyebrow-rule" /> FIRST, A LITTLE CONTEXT</div>
              <h1>Where are you<br />in your <em>ECE journey?</em></h1>
              <p>Choose a study year and section from the records available to Signal. Your selection helps keep timetable and course questions in context.</p>
              <div className="source-note"><span className="source-note-symbol">i</span><span>Only source-supported sections appear here. Signal won’t guess a match.</span></div>
            </div>
            <form className="profile-form" onSubmit={(event) => void saveAcademicProfile(event)}>
              <div className="form-heading"><span>ACADEMIC PROFILE</span><span>REQUIRED</span></div>
              {error && <ErrorNotice message={error} onDismiss={clearError} />}
              {busy === "restore" || busy === "options" ? (
                <div className="loading-state"><span className="loader" /><span>{busy === "restore" ? "Restoring this browser session…" : "Loading available study years and sections…"}</span></div>
              ) : !profileOptions ? (
                <div className="options-unavailable"><p>Profile options could not be loaded from Signal.</p><button className="text-button" type="button" onClick={() => void launch()}><Icon name="retry" size={15} /> Try again</button></div>
              ) : availableYears.length === 0 ? (
                <div className="options-unavailable"><p>No validated study-year options are available yet.</p><button className="text-button" type="button" onClick={() => void launch()}><Icon name="retry" size={15} /> Check again</button></div>
              ) : (
                <>
                  <label className="field-label" htmlFor="study-year">STUDY YEAR</label>
                  <div className="select-wrap"><select id="study-year" value={year} onChange={(event) => { setYear(event.target.value); setSection(""); clearError(); }} required><option value="" disabled>Select your year</option>{availableYears.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select><Icon name="chevron" size={16} /></div>
                  <label className="field-label field-label-spaced" htmlFor="study-section">SECTION</label>
                  <div className={`select-wrap${!year ? " select-disabled" : ""}`}><select id="study-section" value={section} onChange={(event) => { setSection(event.target.value); clearError(); }} required disabled={!year || availableSections.length === 0}><option value="" disabled>{!year ? "Choose a year first" : availableSections.length ? "Select your section" : "No supported section listed"}</option>{availableSections.map((item) => <option value={item} key={item}>{item}</option>)}</select><Icon name="chevron" size={16} /></div>
                  {year && availableSections.length === 0 && <p className="field-hint">No source-supported sections were returned for this year. Please check back later.</p>}
                  <p className="form-footnote">Cohort and semester are left unspecified until Signal has reviewed values for them.</p>
                  <button className="button button-primary button-full" type="submit" disabled={!year || !section || busy !== null}>{busy === "profile" ? "Saving profile…" : "Continue to Signal"}<Icon name="arrow" size={17} /></button>
                </>
              )}
              <div className="form-privacy"><span className="privacy-line" /> NO STUDENT LOGIN REQUIRED</div>
            </form>
          </div>
          <footer className="setup-footer"><span>INDEPENDENT STUDENT PROJECT</span><span>Not an official IIT Roorkee service</span></footer>
        </section>
      )}

      {screen === "workspace" && (
        <section id="workspace" className={`workspace-shell${mobileSidebar ? " sidebar-open" : ""}`}>
          <aside className="workspace-sidebar">
            <div className="sidebar-brand-row"><a className="brand-lockup brand-lockup-light" href="#workspace" aria-label="Signal workspace"><SignalMark /><span>signal<span className="brand-period">.</span></span></a><button className="icon-button sidebar-close" aria-label="Close conversation menu" onClick={() => setMobileSidebar(false)}><Icon name="close" /></button></div>
            <button className="new-chat-button" type="button" onClick={() => void startConversation()} disabled={busy !== null}><Icon name="plus" size={16} /><span>New conversation</span></button>
            <div className="sidebar-label">YOUR CONVERSATIONS <span>{String(conversations.length).padStart(2, "0")}</span></div>
            <nav className="conversation-list" aria-label="Conversations">
              {conversations.length ? conversations.map((item) => <button type="button" key={item.conversation_id} onClick={() => void openConversation(item)} className={`conversation-link${conversationId === item.conversation_id ? " conversation-active" : ""}`} aria-current={conversationId === item.conversation_id ? "page" : undefined} disabled={busy?.startsWith("history:")}><Icon name="message" size={15} /><span>{item.title || "New conversation"}</span></button>) : <p className="conversation-empty">Your conversations will appear here.</p>}
            </nav>
            <div className="sidebar-spacer" />
            <div className="profile-card">
              <span className="profile-card-label">CURRENT PROFILE</span>
              <strong>{profile ? `Year ${profile.study_year} · ${profile.section}` : "Not set"}</strong>
              <button type="button" onClick={() => void changeProfile()} disabled={busy !== null}>Change academic profile <Icon name="arrow" size={14} /></button>
            </div>
            <div className="sidebar-footer"><SignalMark /><span>SOURCE-LED STUDY<br />INDEPENDENT PROJECT</span></div>
          </aside>
          {mobileSidebar && <button className="sidebar-scrim" type="button" onClick={() => setMobileSidebar(false)} aria-label="Close conversation menu" />}

          <div className="workspace-main">
            <header className="workspace-topbar">
              <button className="icon-button mobile-menu" type="button" onClick={() => setMobileSidebar(true)} aria-label="Open conversation menu"><Icon name="menu" /></button>
              <div className="breadcrumb"><span>STUDY DESK</span><span className="breadcrumb-slash">/</span><strong>{profile ? `YEAR ${profile.study_year} · ${profile.section}` : "ACADEMIC PROFILE"}</strong></div>
              <div className="service-status"><span className={`status-dot${health ? "" : " status-offline"}`} />{health ? health.dependencies.database === "ready" ? "SOURCE SERVICE READY" : "SERVICE DEGRADED" : "SERVICE UNAVAILABLE"}</div>
            </header>

            <div className="conversation-body">
              {error && !historyError && <ErrorNotice message={error} onDismiss={clearError} />}
              {health?.dependencies.chat_model === "not_configured" && <div className="capability-note" role="status"><span className="capability-mark"><Icon name="spark" size={15} /></span><p><strong>Source lookups are available.</strong> Open-ended explanations need a chat model, which is not configured yet.</p></div>}

              {historyError ? (
                <div className="history-error"><span className="empty-icon"><Icon name="message" size={22} /></span><h2>Conversation didn’t load.</h2><p>Signal couldn’t retrieve this history. Your other conversations are still available.</p><button className="button button-secondary" type="button" onClick={() => { const item = conversations.find((entry) => entry.conversation_id === conversationId); if (item) void openConversation(item, true); }}>Try again <Icon name="retry" size={15} /></button></div>
              ) : busy === "restore" || busy?.startsWith("history:") ? (
                <div className="history-loading" role="status"><span className="loader" /><span>{busy === "restore" ? "Restoring your conversation…" : "Loading conversation history…"}</span></div>
              ) : !conversationId ? (
                <div className="empty-workspace">
                  <div className="empty-kicker"><span className="eyebrow-rule" /> READY WHEN YOU ARE</div>
                  <span className="empty-icon"><SignalMark large /></span>
                  <h1>A good place to<br /><em>start asking.</em></h1>
                  <p>Explore courses, ask about your timetable, or follow a syllabus topic. Use a shortcut below or ask anything in your own words.</p>
                  <button className="button button-primary empty-new-chat" type="button" onClick={() => void startConversation()} disabled={busy !== null}><Icon name="plus" size={16} /> Start a conversation <Icon name="arrow" size={16} /></button>
                  <div className="quick-prompt-grid">{quickPrompts.map((prompt) => <button type="button" className="quick-prompt" key={prompt.label} onClick={() => void startConversation(prompt.text)} disabled={busy !== null}><Icon name={prompt.icon} size={17} /><span>{prompt.label}</span><Icon name="arrow" size={14} /></button>)}</div>
                </div>
              ) : messages.length === 0 ? (
                <div className="empty-conversation">
                  <div className="empty-kicker"><span className="eyebrow-rule" /> NEW CONVERSATION</div>
                  <span className="empty-icon empty-icon-small"><Icon name="spark" size={21} /></span>
                  <h2>What are you working on?</h2>
                  {busy === "send" ? <div className="history-loading" role="status"><span className="loader" /><span>Checking source records…</span></div> : <><p>Ask a specific question or start with one of these.</p><div className="quick-prompt-grid">{quickPrompts.map((prompt) => <button type="button" className="quick-prompt" key={prompt.label} onClick={() => void sendMessage(prompt.text)} disabled={busy !== null}><Icon name={prompt.icon} size={17} /><span>{prompt.label}</span><Icon name="arrow" size={14} /></button>)}</div></>}
                </div>
              ) : (
                <div className="message-thread" aria-live="polite">
                  {messages.map((message) => <article className={`message message-${message.role}`} key={message.id}>
                    <div className="message-meta"><span className={`message-avatar${message.role === "assistant" ? " assistant-avatar" : ""}`}>{message.role === "assistant" ? <SignalMark /> : "Y"}</span><span className="message-author">{message.role === "assistant" ? "SIGNAL" : "YOU"}</span>{message.role === "assistant" && message.presentation && message.presentation !== "answer" && <span className="message-kind">{presentationNames[message.presentation]}</span>}<time>{displayDate(message.created_at)}</time></div>
                    <div className="message-content">
                      <p className="message-text">{message.content}</p>
                      {message.role === "assistant" && message.presentation && <Records presentation={message.presentation} data={message.data} />}
                      {message.role === "assistant" && Array.isArray(message.warnings) && message.warnings.length > 0 && <div className="message-warnings" aria-label="Source notes"><div className="warning-heading"><span>!</span> SOURCE NOTES</div><ul>{message.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
                      {message.role === "assistant" && <CitationList sources={Array.isArray(message.sources) ? message.sources : []} />}
                      {message.role === "assistant" && <button className="copy-button" type="button" onClick={() => void copyMessage(message)}><Icon name={copied === message.id ? "check" : "copy"} size={13} />{copied === message.id ? "Copied" : "Copy answer"}</button>}
                    </div>
                  </article>)}
                  {busy === "send" && <div className="assistant-thinking" aria-label="Signal is responding"><span /><span /><span /><span className="thinking-label">CHECKING SOURCE RECORDS</span></div>}
                  <div ref={endRef} />
                </div>
              )}
            </div>

            {conversationId && <div className="composer-region">
              <div className="composer-wrap">
                <textarea ref={textareaRef} rows={1} maxLength={4000} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="Ask about a course, timetable, exam, or topic…" aria-label="Your message" disabled={busy !== null} />
                <div className="composer-bottom"><span className="composer-hint"><kbd>Enter</kbd> to send <span>·</span> <kbd>Shift + Enter</kbd> for a new line</span><span className="composer-right"><span className="character-count">{draft.length}/4000</span><button className="send-button" type="button" onClick={() => void sendMessage()} disabled={!draft.trim() || busy !== null} aria-label="Send message"><Icon name="send" size={17} /></button></span></div>
              </div>
              <p className="composer-disclaimer">Signal can only answer from available records. Check each source and note its coverage.</p>
            </div>}
          </div>
        </section>
      )}
    </main>
  );
}
