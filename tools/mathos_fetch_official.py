#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

OUT = Path("MathOS-official-source-fetch")
FILES = OUT / "originals"
PAGES = OUT / "source-pages"
INDEX = OUT / "index"
for p in (FILES, PAGES, INDEX):
    p.mkdir(parents=True, exist_ok=True)

TARGETS = {
    "SRC-0043": {
        "article": 771,
        "title": "2022 개정 교육과정에 따른 초·중학교 영어과 성취수준 개발 연구",
        "crc": "CRC 2024-10",
        "subject": "영어과",
        "min_bytes": 2_000_000,
        "min_pages": 100,
    },
    "SRC-0041": {
        "article": 772,
        "title": "2022 개정 교육과정에 따른 초·중학교 수학과 성취수준 개발 연구",
        "crc": "CRC 2024-8",
        "subject": "수학과",
        "min_bytes": 20_000_000,
        "min_pages": 100,
    },
    "SRC-0042": {
        "article": 773,
        "title": "2022 개정 교육과정에 따른 초·중학교 국어과 성취수준 개발 연구",
        "crc": "CRC 2024-9",
        "subject": "국어과",
        "min_bytes": 2_000_000,
        "min_pages": 100,
    },
    "SRC-0040": {
        "article": 785,
        "title": "2022 개정 교육과정에 따른 초·중학교 성취수준 개발 연구(총론)",
        "crc": "CRC 2024-11",
        "subject": "총론",
        "min_bytes": 3_000_000,
        "min_pages": 100,
    },
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MathOS-Official-Source-Audit/1.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
})


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("ㆍ", "·").replace("･", "·").replace("․", "·")
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", text).lower()


def get(url: str, *, timeout: int = 90) -> requests.Response:
    r = SESSION.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


def pdf_text(path: Path, max_pages: int = 40) -> tuple[str, int]:
    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages[: min(len(reader.pages), max_pages)]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
    return "\n".join(chunks), len(reader.pages)


def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "download.pdf"


records = []
failures = []

for source_id, target in TARGETS.items():
    page_url = f"https://ncic.re.kr/bbs/standard/view/{target['article']}.do"
    try:
        page_resp = get(page_url)
    except Exception as exc:
        failures.append({"source_id": source_id, "stage": "page", "error": repr(exc), "url": page_url})
        continue

    page_html = page_resp.text
    (PAGES / f"{source_id}__article-{target['article']}.html").write_text(page_html, encoding="utf-8")
    soup = BeautifulSoup(page_html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a.get("href", ""))
        if "/bbs/download.do" not in href:
            continue
        context = " ".join(a.parent.stripped_strings) if a.parent else a.get_text(" ", strip=True)
        links.append((href, context))

    if not links:
        failures.append({"source_id": source_id, "stage": "parse", "error": "No NCIC download links", "url": page_url})
        continue

    verified = None
    candidate_log = []
    for idx, (download_url, context) in enumerate(links, start=1):
        if ".pdf" not in context.lower() and ".pdf" not in download_url.lower():
            continue
        try:
            response = get(download_url, timeout=180)
            data = response.content
        except Exception as exc:
            candidate_log.append({"url": download_url, "context": context, "decision": "DOWNLOAD_FAILED", "error": repr(exc)})
            continue

        sha = hashlib.sha256(data).hexdigest()
        if not data.startswith(b"%PDF-"):
            candidate_log.append({"url": download_url, "context": context, "size_bytes": len(data), "sha256": sha, "decision": "REJECT_NON_PDF_SIGNATURE"})
            continue

        temp = FILES / f"_{source_id}_candidate_{idx}.pdf"
        temp.write_bytes(data)
        try:
            text, pages = pdf_text(temp)
        except Exception as exc:
            candidate_log.append({"url": download_url, "context": context, "size_bytes": len(data), "sha256": sha, "decision": "REJECT_PDF_PARSE", "error": repr(exc)})
            temp.unlink(missing_ok=True)
            continue

        nt = norm(text)
        title_ok = norm(target["title"]) in nt
        crc_ok = norm(target["crc"]) in nt
        subject_ok = norm(target["subject"]) in nt
        size_ok = len(data) >= target["min_bytes"]
        pages_ok = pages >= target["min_pages"]
        candidate = {
            "url": download_url,
            "context": context,
            "size_bytes": len(data),
            "sha256": sha,
            "pdf_pages": pages,
            "title_ok": title_ok,
            "crc_ok": crc_ok,
            "subject_ok": subject_ok,
            "size_ok": size_ok,
            "pages_ok": pages_ok,
        }
        if title_ok and crc_ok and subject_ok and size_ok and pages_ok:
            canonical = safe_name(f"{source_id}__NCIC__{target['crc'].replace(' ', '-')}__official-report.pdf")
            final_path = FILES / canonical
            shutil.move(str(temp), str(final_path))
            verified = {
                "source_id": source_id,
                "title": target["title"],
                "publisher": "한국교육과정평가원·교육부",
                "official_page_url": page_url,
                "official_download_url": download_url,
                "file_name": canonical,
                "relative_path": final_path.as_posix(),
                "size_bytes": len(data),
                "sha256": sha,
                "signature": "PDF",
                "pdf_pages": pages,
                "crc": target["crc"],
                "exact_title_verified": True,
                "exact_crc_verified": True,
                "decision": "VERIFIED_OFFICIAL_ORIGINAL",
                "rights_status": "RIGHTS_UNREVIEWED",
            }
            candidate["decision"] = "VERIFIED_OFFICIAL_ORIGINAL"
            candidate_log.append(candidate)
            break
        candidate["decision"] = "REJECT_CONTENT_MISMATCH"
        candidate_log.append(candidate)
        temp.unlink(missing_ok=True)

    records.extend(candidate_log)
    if verified:
        records.append(verified)
    else:
        failures.append({"source_id": source_id, "stage": "verification", "error": "No candidate passed exact title, CRC, subject, size and page checks", "page_url": page_url})

verified_rows = [r for r in records if r.get("decision") == "VERIFIED_OFFICIAL_ORIGINAL" and r.get("source_id")]
summary = {
    "targets": list(TARGETS),
    "verified_source_ids": sorted({r["source_id"] for r in verified_rows}),
    "verified_original_count": len(verified_rows),
    "failed_source_ids": sorted({f["source_id"] for f in failures}),
    "failures": failures,
    "promotion_to_user_vault": "NOT_PERFORMED",
}

(INDEX / "manifest.json").write_text(json.dumps(verified_rows, ensure_ascii=False, indent=2), encoding="utf-8")
(INDEX / "audit-log.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
(INDEX / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
with (INDEX / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
    keys = ["source_id", "title", "publisher", "official_page_url", "official_download_url", "file_name", "relative_path", "size_bytes", "sha256", "signature", "pdf_pages", "crc", "exact_title_verified", "exact_crc_verified", "decision", "rights_status"]
    w = csv.DictWriter(f, fieldnames=keys)
    w.writeheader()
    for row in verified_rows:
        w.writerow({k: row.get(k, "") for k in keys})

print(json.dumps(summary, ensure_ascii=False, indent=2))
if not verified_rows:
    sys.exit(2)
