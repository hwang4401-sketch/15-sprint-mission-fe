#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests
from pypdf import PdfReader

OUT = Path("MathOS-official-source-diagnostics")
FILES = OUT / "candidates"
TEXT = OUT / "extracted-text"
INDEX = OUT / "index"
for p in (FILES, TEXT, INDEX):
    p.mkdir(parents=True, exist_ok=True)

URLS = {
    "SRC-0041-candidate-1": "https://ncic.re.kr/bbs/download.do?articleIdx=772&fileName=1725497528110.pdf",
    "SRC-0041-candidate-2": "https://ncic.re.kr/bbs/download.do?articleIdx=772&fileName=1725497528783.pdf",
    "SRC-0040-candidate-1": "https://ncic.re.kr/bbs/download.do?articleIdx=785&fileName=1761720155556_ohzy.pdf",
    "SRC-0040-candidate-2": "https://ncic.re.kr/bbs/download.do?articleIdx=785&fileName=1761720155590_107r.pdf",
    "SRC-0040-candidate-3": "https://ncic.re.kr/bbs/download.do?articleIdx=785&fileName=1761720155599_tsps.pdf",
}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 MathOS-Official-Source-Audit/1.1"})
rows = []
for label, url in URLS.items():
    row = {"label": label, "url": url}
    try:
        r = session.get(url, timeout=240, allow_redirects=True)
        r.raise_for_status()
        data = r.content
        path = FILES / f"{label}.pdf"
        path.write_bytes(data)
        row["size_bytes"] = len(data)
        row["sha256"] = hashlib.sha256(data).hexdigest()
        row["pdf_signature"] = data.startswith(b"%PDF-")
        reader = PdfReader(str(path))
        row["pdf_pages"] = len(reader.pages)
        chunks = []
        for i, page in enumerate(reader.pages[:60]):
            try:
                chunks.append(f"\n===== PAGE {i+1} =====\n" + (page.extract_text() or ""))
            except Exception as exc:
                chunks.append(f"\n===== PAGE {i+1} ERROR {exc!r} =====\n")
        text = "".join(chunks)
        (TEXT / f"{label}.txt").write_text(text, encoding="utf-8")
        row["extracted_text_chars"] = len(text)
        row["status"] = "DOWNLOADED_FOR_DIRECT_REVIEW"
    except Exception as exc:
        row["status"] = "FAILED"
        row["error"] = repr(exc)
    rows.append(row)

(INDEX / "diagnostic-manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(rows, ensure_ascii=False, indent=2))
