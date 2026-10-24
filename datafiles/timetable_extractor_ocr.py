#!/usr/bin/env python3
"""
timetable_extractor_ocr.py

Extract ECE timetable data from the supplied image-based timetable PDF.

This version is designed for the Autumn 2026-27 ECE timetable PDF where:
- there is one timetable page per year (I, II, III, IV year),
- the PDF has no usable text layer, so pages are rendered and OCR'd,
- every class entry starts with one of:
      L = Lecture
      T = Tutorial
      P = Practical / Lab
- cells may contain multiple entries stacked vertically.

Outputs:
    <output>.csv
    <output>.json
    <output>_by_year.json

Each record includes year, day, slot time, session type, course, batch,
room, faculty, sections, raw OCR text and source page.

Dependencies:
    pip install pymupdf opencv-python pytesseract numpy scipy

Also install the Tesseract OCR engine separately on Windows/Linux and make
sure `tesseract` is on PATH. On Windows you can pass --tesseract-cmd.

Example:
    python timetable_extractor_ocr.py timetable.pdf --output master_timetable.csv

If Tesseract is not in PATH:
    python timetable_extractor_ocr.py timetable.pdf \
        --tesseract-cmd "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import fitz  # PyMuPDF
import numpy as np
import pytesseract
from pytesseract import Output
from scipy.signal import find_peaks


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# The timetable uses these fixed class slots on every page.
TIME_SLOTS = [
    ("08:00", "08:55"),
    ("09:00", "09:55"),
    ("10:00", "10:55"),
    ("11:05", "12:00"),
    ("12:05", "13:00"),
    ("13:00", "14:00"),  # Lunch row; not emitted as a class record.
    ("14:00", "14:55"),
    ("15:00", "15:55"),
    ("16:05", "17:00"),
    ("17:05", "18:00"),
    ("18:05", "19:00"),
]

TIME_STARTS = [
    "08.00-",
    "09.00-",
    "10.00-",
    "11.05-",
    "12.05-",
    "13.00-",
    "14.00-",
    "15.00-",
    "16.05-",
    "17.05-",
    "18.05-",
]

YEAR_BY_PAGE = {
    1: "I-Year",
    2: "II-Year",
    3: "III-Year",
    4: "IV-Year",
}

# Room/building prefixes visible in the supplied ECE timetable.
BUILDING_PREFIXES = {"AKB", "GB", "LH"}

BATCH_RE = re.compile(r"\bBatch\s*(\d+)\b", re.IGNORECASE)
CODE_RE = re.compile(r"\b([A-Z]{2,5})\s*-\s*(\d{2,4})\b")
SECTION_RE = re.compile(r"\b\d{2}[A-Z]{2}\d\b")

# Important: require whitespace after L/T/P. This prevents a faculty name such
# as "P. Pathak" from being misread as a new Practical entry.
TYPE_RE = re.compile(r"^\s*([LTP])(?=\s)", re.IGNORECASE)

SESSION_NAMES = {
    "L": "Lecture",
    "T": "Tutorial",
    "P": "Practical",
}


def normalize_text(text: str) -> str:
    """Normalize common OCR artifacts without destroying line structure."""
    text = text.replace("\r", "\n")

    # Course/room codes sometimes break across an OCR newline:
    # CSE-\n101 -> CSE-101
    text = re.sub(
        r"([A-Za-z]{2,5})\s*-\s*\n\s*(\d{2,4})",
        r"\1-\2",
        text,
    )
    text = re.sub(
        r"([A-Za-z]{2,5})\s+-\s+(\d{2,4})",
        r"\1-\2",
        text,
    )

    # Common OCR confusion for OEC.
    text = re.sub(r"\b0EC\b", "OEC", text, flags=re.IGNORECASE)

    # OCR may glue the session letter to the course, e.g. PECC-535 or LOEC.
    text = re.sub(
        r"^\s*([LTP])(?=[A-Z]{2,5}-\d{2,4}\b)",
        r"\1 ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^\s*([LTP])(?=OEC\b)", r"\1 ", text, flags=re.IGNORECASE)

    # OCR can glue a room prefix to the preceding word, e.g. DoMSLH-01.
    text = re.sub(
        r"(?<=[A-Za-z])(?=(?:AKB|GB|LH)-\d{2,4}\b)",
        " ",
        text,
    )

    # Standardize line endings only; line structure is useful for splitting cells.
    return text


def split_cell_into_entries(cell_text: str) -> List[str]:
    """Split a cell containing one or more stacked L/T/P entries."""
    text = normalize_text(cell_text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]

    entries: List[str] = []
    current: List[str] = []

    for line in lines:
        # Normalize glued session prefix on individual OCR lines too.
        line = re.sub(
            r"^([LTP])(?=[A-Z]{2,5}-\d{2,4}\b)",
            r"\1 ",
            line,
            flags=re.IGNORECASE,
        )
        line = re.sub(r"^([LTP])(?=OEC\b)", r"\1 ", line, flags=re.IGNORECASE)

        if TYPE_RE.match(line):
            if current:
                entries.append(" ".join(current))
            current = [line]
        elif current:
            current.append(line)
        else:
            # Keep leading OCR text rather than silently discarding it.
            current = [line]

    if current:
        entries.append(" ".join(current))

    # In case Tesseract collapses multiple entries onto one physical line.
    output: List[str] = []
    for entry in entries:
        parts = re.split(r"(?=\b[LTP]\s+[A-Z0-9])", entry)
        output.extend(part.strip(" ,") for part in parts if part.strip())

    return output


def parse_entry(raw_text: str) -> Dict:
    """Parse one L/T/P timetable entry into structured fields."""
    text = normalize_text(raw_text)
    original = " ".join(text.split())

    entry = {
        "session_type": None,
        "session_type_code": None,
        "course_code": None,
        "batch": None,
        "room": None,
        "faculty": None,
        "sections": None,
        "unmatched_codes": [],
        "raw_text": original,
    }

    # 1. Session type comes from the FIRST character/token.
    type_match = TYPE_RE.match(text)
    if type_match:
        type_code = type_match.group(1).upper()
        entry["session_type_code"] = type_code
        entry["session_type"] = SESSION_NAMES[type_code]
        text = text[type_match.end() :]

    # 2. Remove known building-complex marker words.
    #    Repeated after room-glue repair so DoMSLH-01 becomes removable.
    text = re.sub(r"\b(?:APJ|DoMS)\b", " ", text, flags=re.IGNORECASE)

    # 3. Batch.
    batch_match = BATCH_RE.search(text)
    if batch_match:
        entry["batch"] = batch_match.group(1)
        text = text[: batch_match.start()] + " " + text[batch_match.end() :]

    # 4. Sections such as 26EC1,26EC2,...
    sections = SECTION_RE.findall(text)
    if sections:
        entry["sections"] = ",".join(sections)
        text = SECTION_RE.sub(" ", text)

    # 5. Course / room codes.
    for code_match in CODE_RE.finditer(text):
        prefix = code_match.group(1).upper()
        code = f"{prefix}-{code_match.group(2)}"

        if prefix in BUILDING_PREFIXES and entry["room"] is None:
            entry["room"] = code
        elif entry["course_code"] is None:
            entry["course_code"] = code
        else:
            entry["unmatched_codes"].append(code)

    text = CODE_RE.sub(" ", text)

    # OEC is printed as a plain token rather than OEC-xxx.
    if entry["course_code"] is None:
        oec_match = re.search(r"\bOEC\b", text, flags=re.IGNORECASE)
        if oec_match:
            entry["course_code"] = "OEC"
            text = text[: oec_match.start()] + " " + text[oec_match.end() :]

    # 6. Remaining text is normally the faculty name.
    text = re.sub(r"\b(?:APJ|DoMS)\b", " ", text, flags=re.IGNORECASE)
    faculty = re.sub(r"\s+", " ", text).strip(" ,.-")
    entry["faculty"] = faculty or None

    return entry


def render_pdf(pdf_path: Path, dpi: int) -> List[np.ndarray]:
    """Render every PDF page to an OpenCV BGR image."""
    document = fitz.open(pdf_path)
    scale = dpi / 72.0
    images: List[np.ndarray] = []

    try:
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            arr = np.frombuffer(pixmap.samples, np.uint8).reshape(
                pixmap.height, pixmap.width, pixmap.n
            )
            if pixmap.n == 4:
                image = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            else:
                image = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            images.append(image)
    finally:
        document.close()

    return images


def detect_x_edges(image: np.ndarray) -> List[int]:
    """Detect the six timetable column boundaries from the header/grid."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    header = gray[98 : min(image.shape[0], 160), :]
    horizontal_gradient = np.abs(np.diff(header, axis=1)).mean(axis=0)

    peaks, _ = find_peaks(
        horizontal_gradient,
        distance=120,
        prominence=30,
    )

    candidates = sorted(
        [
            (float(horizontal_gradient[i]), int(i))
            for i in peaks
            if horizontal_gradient[i] > 30
        ],
        key=lambda value: value[1],
    )

    x_edges: List[int] = []
    for strength, x in candidates:
        if not x_edges or x - x_edges[-1] > 8:
            x_edges.append(x)
        elif strength > 0:
            x_edges[-1] = x

    # Drop text-induced peaks; the timetable has exactly five day columns plus
    # the Time/Day column, so we expect seven boundaries.
    x_edges = [x for x in x_edges if x > 40]
    x_edges = [0] + x_edges

    if len(x_edges) != 7:
        raise RuntimeError(
            f"Expected 7 vertical table boundaries but detected {x_edges}. "
            "Try increasing --dpi or inspect the page image."
        )

    return x_edges


def detect_row_starts(image: np.ndarray, time_column_right: int) -> List[int]:
    """Locate the 11 timetable rows from OCR'd time labels."""
    crop_y0 = 95

    # Keep the crop narrow. Including the first day column makes Tesseract
    # occasionally skip some of the smaller time labels.
    crop_width = min(60, max(45, time_column_right - 5))
    crop = image[crop_y0 : min(image.shape[0], 1900), 0:crop_width]

    scale = 3
    enlarged = cv2.resize(
        crop,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC,
    )

    data = pytesseract.image_to_data(
        enlarged,
        config="--psm 6",
        output_type=Output.DATAFRAME,
    )
    data = data.dropna(subset=["text", "top", "conf"])

    label_positions: Dict[str, float] = {}
    for _, row in data.iterrows():
        token = str(row["text"]).strip().replace(" ", "")
        if token in TIME_STARTS and token not in label_positions:
            label_positions[token] = crop_y0 + float(row["top"]) / scale

    missing = [token for token in TIME_STARTS if token not in label_positions]
    if missing:
        raise RuntimeError(
            "Could not OCR these timetable row labels: " + ", ".join(missing)
        )

    # The first line of each time label sits ~15 px below the actual row top.
    # Moving upward by 20 px gives a small safety margin without clipping the cell.
    return [int(round(label_positions[token] - 20)) for token in TIME_STARTS]


def detect_header(image: np.ndarray, page_number: int) -> Tuple[str, str, str]:
    """OCR the header for term/academic year, with safe page-based fallback."""
    header = image[0:98, :]
    enlarged = cv2.resize(header, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    header_text = pytesseract.image_to_string(enlarged, config="--psm 6")

    academic_year_match = re.search(r"(20\d{2}-\d{2})", header_text)
    academic_year = academic_year_match.group(1) if academic_year_match else "2026-27"
    term = "Autumn" if re.search(r"Autumn", header_text, re.IGNORECASE) else ""

    year = YEAR_BY_PAGE.get(page_number, f"Page-{page_number}")
    return term, academic_year, year


def process_page(image: np.ndarray, page_number: int) -> List[Dict]:
    """Extract all class entries from one timetable page."""
    x_edges = detect_x_edges(image)
    row_starts = detect_row_starts(image, x_edges[1])
    term, academic_year, year = detect_header(image, page_number)

    row_bounds: List[Tuple[int, int]] = []
    for i, start in enumerate(row_starts):
        if i + 1 < len(row_starts):
            end = row_starts[i + 1]
        else:
            # The last row is followed by blank page area; a generous crop is safe.
            end = min(image.shape[0] - 20, start + 220)
        row_bounds.append((max(0, start), max(0, end)))

    records: List[Dict] = []

    for row_index, (y0, y1) in enumerate(row_bounds):
        # Row 5 (13:00-14:00) is lunch.
        if row_index == 5:
            continue

        start_time, end_time = TIME_SLOTS[row_index]

        for day_index, day in enumerate(DAYS):
            x0 = x_edges[day_index + 1]
            x1 = x_edges[day_index + 2]

            # Small border trim; keep all cell text.
            cell = image[y0 + 3 : y1 - 3, x0 + 3 : x1 - 3]
            enlarged = cv2.resize(
                cell,
                None,
                fx=3,
                fy=3,
                interpolation=cv2.INTER_CUBIC,
            )

            ocr_text = pytesseract.image_to_string(enlarged, config="--psm 6")
            if not ocr_text.strip():
                continue

            for entry_text in split_cell_into_entries(ocr_text):
                parsed = parse_entry(entry_text)

                # Ignore residual OCR junk that has neither a session type nor
                # a course code.
                if not parsed["session_type"] and not parsed["course_code"]:
                    continue

                parsed.update(
                    {
                        "term": term,
                        "academic_year": academic_year,
                        "year": year,
                        "day": day,
                        "start_time": start_time,
                        "end_time": end_time,
                        "source_page": page_number,
                    }
                )
                records.append(parsed)

    return records


def write_outputs(records: List[Dict], output_csv: Path) -> None:
    """Write flat CSV/JSON plus JSON grouped by year."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json = output_csv.with_suffix(".json")
    grouped_json = output_csv.with_name(output_csv.stem + "_by_year.json")

    fieldnames = [
        "term",
        "academic_year",
        "year",
        "day",
        "start_time",
        "end_time",
        "session_type_code",
        "session_type",
        "course_code",
        "batch",
        "room",
        "faculty",
        "sections",
        "unmatched_codes",
        "raw_text",
        "source_page",
    ]

    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["unmatched_codes"] = ";".join(record.get("unmatched_codes") or [])
            writer.writerow(row)

    output_json.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for record in records:
        grouped[record["year"]].append(record)

    grouped_json.write_text(
        json.dumps(dict(grouped), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nExtracted {len(records)} class entries.")
    print(f"CSV : {output_csv}")
    print(f"JSON: {output_json}")
    print(f"BY YEAR: {grouped_json}")

    for year in ["I-Year", "II-Year", "III-Year", "IV-Year"]:
        count = len(grouped.get(year, []))
        print(f"  {year}: {count} entries")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="Timetable PDF")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("master_timetable.csv"),
        help="Output CSV path (JSON files are created next to it)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="PDF rendering DPI (200 is a good default; 250-300 can improve OCR)",
    )
    parser.add_argument(
        "--tesseract-cmd",
        type=str,
        default="",
        help="Full path to tesseract.exe if it is not on PATH",
    )
    args = parser.parse_args()

    if args.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = args.tesseract_cmd

    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    try:
        print(f"Rendering {args.pdf} at {args.dpi} DPI...")
        images = render_pdf(args.pdf, args.dpi)
    except Exception as exc:
        raise SystemExit(f"Could not render PDF: {exc}") from exc

    all_records: List[Dict] = []

    for page_number, image in enumerate(images, start=1):
        print(f"Processing page {page_number}/{len(images)}...")
        try:
            page_records = process_page(image, page_number)
        except Exception as exc:
            raise SystemExit(f"Page {page_number} failed: {exc}") from exc

        print(f"  -> {len(page_records)} class entries")
        all_records.extend(page_records)

    if not all_records:
        raise SystemExit("No timetable entries extracted.")

    write_outputs(all_records, args.output)


if __name__ == "__main__":
    main()
