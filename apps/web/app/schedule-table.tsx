type Row = Record<string, unknown>;
const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const value = (input: unknown) => typeof input === "string" || typeof input === "number" ? String(input) : "";

function time(input: unknown) {
  const raw = value(input);
  const match = /^(\d{1,2}):(\d{2})$/.exec(raw);
  if (!match) return raw;
  const hour = Number(match[1]);
  return `${hour % 12 || 12}:${match[2]} ${hour < 12 ? "AM" : "PM"}`;
}

function date(input: unknown) {
  const raw = value(input);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(raw));
}

export default function ScheduleTable({ records, exams = false }: { records: Row[]; exams?: boolean }) {
  const ordered = [...records].sort((a, b) => exams
    ? value(a.exam_date).localeCompare(value(b.exam_date)) || value(a.start_time).localeCompare(value(b.start_time))
    : days.indexOf(value(a.day)) - days.indexOf(value(b.day)) || value(a.start_time).localeCompare(value(b.start_time)));
  const groups = exams ? ["Exams"] : days.filter((day) => ordered.some((row) => row.day === day));
  if (!exams && ordered.some((row) => !days.includes(value(row.day)))) groups.push("Other sessions");
  return <section className={`schedule-block${exams ? " schedule-exams" : ""}`} aria-label={exams ? "Exam schedule" : "Weekly timetable"}>
    {groups.map((day) => <div className="schedule-day" key={day}>
      {!exams && <h3>{day}</h3>}
      <div className="schedule-scroll" tabIndex={0} role="region" aria-label={exams ? "Exam schedule table" : `${day} timetable`}>
        <table className="schedule-table"><thead><tr>
          {exams && <th>Date</th>}<th>Time</th><th>Course</th><th>{exams ? "Venue" : "Class"}</th>{!exams && <th>Room</th>}
        </tr></thead><tbody>{ordered.filter((row) => exams || row.day === day || (day === "Other sessions" && !days.includes(value(row.day)))).map((row, index) => {
          const clashes = Array.isArray(row.clashes_with) ? row.clashes_with : [];
          return <tr key={value(row.record_id) || index} className={clashes.length ? "timetable-clash" : undefined}>
            {exams && <td className="schedule-date">{date(row.exam_date)}<small>{value(row.day)}</small></td>}
            <td className="schedule-time">{time(row.start_time)}<span>– {time(row.end_time)}</span>{exams && row.slot ? <small>Slot {value(row.slot)}</small> : null}</td>
            <td className="schedule-course"><strong>{value(row.course_code)}</strong>{row.course_title ? <span>{value(row.course_title)}</span> : null}
              {!exams && row.faculty ? <small>{value(row.faculty).replace(/,\s*/g, ", ")}</small> : null}
              {clashes.length > 0 && <small className="schedule-conflict">Clashes with {clashes.map(value).join(", ")}</small>}
            </td>
            <td>{exams ? value(row.room) || "—" : <>{value(row.session_type)}{row.course_batch ? <small>Batch {value(row.course_batch)}</small> : null}</>}</td>
            {!exams && <td>{value(row.room) || "—"}</td>}
          </tr>;
        })}</tbody></table>
      </div>
    </div>)}
  </section>;
}
