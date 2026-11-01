import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Older saved replies can contain provenance boilerplate alongside the answer.
export function displayAnswer(text: string) {
  return text.split("\n").filter((line) => !(
    /\b(applicability|unverified|source[- ]backed record|source record;|verify independently)\b/i.test(line)
    || /not an official .* (equivalent|source)|not a verified match|records do not confirm facts/i.test(line)
  )).join("\n").trim();
}

export default function ChatContent({ text }: { text: string }) {
  return <div className="message-text markdown-content">
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
      a: ({ children, href }) => href ? <a href={href} target="_blank" rel="noreferrer">{children}</a> : <span>{children}</span>,
      table: ({ children }) => <div className="markdown-table-wrap" tabIndex={0} role="region" aria-label="Answer table"><table>{children}</table></div>,
    }}>{displayAnswer(text)}</ReactMarkdown>
  </div>;
}
