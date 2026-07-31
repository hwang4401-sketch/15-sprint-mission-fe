#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import gdown
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path("MathOS-remaining-official-sources").resolve()
ORIGINALS = ROOT / "originals"
PAGES = ROOT / "source-pages"
INDEX = ROOT / "index"
STAGING = ROOT / "staging"
for directory in (ORIGINALS, PAGES, INDEX, STAGING):
    directory.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MathOS-Official-Source-Audit/7.0"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
})

SJE_PAGES = [
    {
        "source_id": "SRC-0044",
        "category": "content-production",
        "url": "https://www.sje.go.kr/sje/na/ntt/selectNttInfo.do?mi=52119&nttSn=3017872",
    },
    {
        "source_id": "SRC-0044",
        "category": "content-production",
        "url": "https://www.sje.go.kr/sje/na/ntt/selectNttInfo.do?mi=52119&nttSn=3017873",
    },
    {
        "source_id": "SRC-0049",
        "category": "math-remediation",
        "url": "https://www.sje.go.kr/ssok/na/ntt/selectNttInfo.do?mi=52288&nttSn=3005934",
    },
    {
        "source_id": "SRC-0049",
        "category": "math-remediation",
        "url": "https://www.sje.go.kr/sje/na/ntt/selectNttInfo.do?mi=52522&nttSn=372646",
    },
    {
        "source_id": "SRC-0049",
        "category": "math-remediation",
        "url": "https://www.sje.go.kr/ssok/na/ntt/selectNttInfo.do?mi=52288&nttSn=3005935",
    },
]

DANDI_PAGE = "https://dandi.pen.go.kr/board/repository/detail?noticeId=144&page=1"
DANDI_FOLDER_ID = "1OYH46rr71gEqdS6gGwbLv8rQdjsFDe7x"
DANDI_FOLDER_URL = f"https://drive.google.com/drive/folders/{DANDI_FOLDER_ID}"

EXPECTED_0044 = {
    "general": {
        "keywords": ["편수자료", "편수일반"],
        "canonical": "SRC-0044__MOE-SJE__textbook-compilation-I-general.pdf",
    },
    "humanities": {
        "keywords": ["편수자료", "인문사회과학"],
        "canonical": "SRC-0044__MOE-SJE__textbook-compilation-II-humanities-social-sciences.pdf",
    },
    "arts": {
        "keywords": ["편수자료", "체육", "음악", "미술"],
        "canonical": "SRC-0044__MOE-SJE__textbook-compilation-II-physical-education-music-art.pdf",
    },
    "science-info": {
        "keywords": ["편수자료", "기초과학", "정보"],
        "canonical": "SRC-0044__MOE-SJE__textbook-compilation-III-basic-science-information.pdf",
    },
}

EXPECTED_0049 = {
    "g1s1": {
        "keywords": ["촘촘", "수학", "1학년", "1학기"],
        "canonical": "SRC-0049__SJE__chomchom-math-grade1-semester1.pdf",
    },
    "g1s2": {
        "keywords": ["촘촘", "수학", "1학년", "2학기"],
        "canonical": "SRC-0049__SJE__chomchom-math-grade1-semester2.pdf",
    },
    "g2s1": {
        "keywords": ["촘촘", "수학", "2학년", "1학기"],
        "canonical": "SRC-0049__SJE__chomchom-math-grade2-semester1.pdf",
    },
    "g2s2": {
        "keywords": ["촘촘", "수학", "2학년", "2학기"],
        "canonical": "SRC-0049__SJE__chomchom-math-grade2-semester2.pdf",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(value: str) -> str:
    value = urllib.parse.unquote_plus(value or "")
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", value).lower()


def safe_name(value: str) -> str:
    value = urllib.parse.unquote_plus(value or "")
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:220] or "attachment.pdf"


def save_page(url: str, label: str) -> str:
    response = SESSION.get(url, timeout=120, allow_redirects=True)
    response.raise_for_status()
    target = PAGES / f"{label}.html"
    target.write_bytes(response.content)
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def extract_sje_attachments(page_text: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(page_text, "html.parser")
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        match = re.search(r"goFileDown\(['\"]([0-9a-fA-F]{32})['\"]\)", href)
        if not match:
            continue
        key = match.group(1)
        if key in seen:
            continue
        seen.add(key)
        title = anchor.get("title") or anchor.get_text(" ", strip=True)
        found.append({"file_key": key, "display_name": safe_name(title)})

    # Some official pages render attachments through DEXT5 JavaScript. Preserve these too.
    pattern = re.compile(
        r"DEXT5UPLOAD\.AddUploadedFile\([^,]+,\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'",
        re.I,
    )
    for match in pattern.finditer(page_text):
        display_name, server_path, size_text, file_id = match.groups()
        display_name = safe_name(display_name)
        existing = next((row for row in found if normalize(row["display_name"]) == normalize(display_name)), None)
        if existing:
            existing.update({"server_path": server_path, "declared_size": size_text, "file_id": file_id})
        else:
            found.append({
                "file_key": "",
                "display_name": display_name,
                "server_path": server_path,
                "declared_size": size_text,
                "file_id": file_id,
            })
    return found


def pdf_text(path: Path, max_pages: int = 35) -> tuple[int, str]:
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages[: min(len(reader.pages), max_pages)]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
    return len(reader.pages), "\n".join(chunks)


def verify_pdf(path: Path, minimum_pages: int) -> tuple[int, str]:
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise RuntimeError(f"PDF signature mismatch: {path}")
    pages, text = pdf_text(path)
    if pages < minimum_pages:
        raise RuntimeError(f"Unexpectedly short PDF: {path.name}, pages={pages}")
    return pages, text


def classify_0044(display_name: str, text: str) -> str | None:
    haystack = normalize(display_name + " " + text[:15000])
    if "편수일반" in haystack:
        return "general"
    if "인문사회과학" in haystack:
        return "humanities"
    if all(word in haystack for word in ("체육", "음악", "미술")):
        return "arts"
    if "기초과학" in haystack and "정보" in haystack:
        return "science-info"
    return None


def classify_0049(display_name: str, text: str) -> str | None:
    haystack = normalize(display_name + " " + text[:15000])
    if "촘촘" not in haystack or "수학" not in haystack:
        return None
    if "1학년" in haystack and "1학기" in haystack:
        return "g1s1"
    if "1학년" in haystack and "2학기" in haystack:
        return "g1s2"
    if "2학년" in haystack and "1학기" in haystack:
        return "g2s1"
    if "2학년" in haystack and "2학기" in haystack:
        return "g2s2"
    return None


def download_sje_attachment(file_key: str, source_page: str, temp_path: Path) -> dict[str, str]:
    url = f"https://www.sje.go.kr/comm/nttFileDownload.do?fileKey={file_key}"
    response = SESSION.get(url, headers={"Referer": source_page}, timeout=300, allow_redirects=True)
    response.raise_for_status()
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(response.content)
    return {
        "requested_url": url,
        "final_url": response.url,
        "content_type": response.headers.get("content-type", ""),
        "content_disposition": response.headers.get("content-disposition", ""),
    }


def acquire_sje(records: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
    candidates: list[dict[str, str]] = []
    for page_number, spec in enumerate(SJE_PAGES, start=1):
        try:
            text = save_page(spec["url"], f"{spec['source_id']}__SJE__page-{page_number}")
            attachments = extract_sje_attachments(text)
            for attachment in attachments:
                attachment.update(spec)
                candidates.append(attachment)
        except Exception as exc:
            errors.append({"stage": "SJE_PAGE", "url": spec["url"], "error": repr(exc)})

    (INDEX / "sje-attachment-candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    accepted: dict[tuple[str, str], dict[str, Any]] = {}
    seen_hashes: set[str] = set()
    for position, candidate in enumerate(candidates, start=1):
        key = candidate.get("file_key") or ""
        display_name = candidate.get("display_name") or ""
        if not key or ".pdf" not in display_name.lower():
            continue
        temp_path = STAGING / "sje" / f"{position:03d}__{safe_name(display_name)}"
        try:
            download_meta = download_sje_attachment(key, candidate["url"], temp_path)
            pages, text = verify_pdf(temp_path, 25 if candidate["source_id"] == "SRC-0044" else 35)
            file_hash = sha256(temp_path)
            if file_hash in seen_hashes:
                continue
            seen_hashes.add(file_hash)

            if candidate["source_id"] == "SRC-0044":
                kind = classify_0044(display_name, text)
                expected = EXPECTED_0044
            else:
                kind = classify_0049(display_name, text)
                expected = EXPECTED_0049
            if not kind:
                errors.append({
                    "stage": "SJE_CLASSIFY",
                    "source_id": candidate["source_id"],
                    "display_name": display_name,
                    "sha256": file_hash,
                    "pages": pages,
                    "error": "target title/grade/semester could not be confirmed",
                })
                continue

            target = ORIGINALS / candidate["category"] / expected[kind]["canonical"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_path, target)
            row = {
                "source_id": candidate["source_id"],
                "title": display_name,
                "publisher": "교육부 자료 / 세종특별자치시교육청 공식 게시",
                "source_page_url": candidate["url"],
                "official_attachment_url": download_meta["final_url"],
                "file_key": key,
                "file_name": target.name,
                "relative_path": target.relative_to(ROOT).as_posix(),
                "size_bytes": target.stat().st_size,
                "sha256": sha256(target),
                "signature": "PDF",
                "pdf_pages": pages,
                "classification": kind,
                "status": "CANDIDATE_VERIFIED",
                "rights_status": "RIGHTS_UNREVIEWED",
            }
            accepted[(candidate["source_id"], kind)] = row
        except Exception as exc:
            errors.append({
                "stage": "SJE_DOWNLOAD_VERIFY",
                "source_id": candidate["source_id"],
                "display_name": display_name,
                "file_key": key,
                "error": repr(exc),
            })

    records.extend(accepted.values())


def acquire_dandi(records: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
    try:
        page_text = save_page(DANDI_PAGE, "SRC-0046__PEN-DANDI__notice-144")
    except Exception as exc:
        errors.append({"stage": "DANDI_PAGE", "url": DANDI_PAGE, "error": repr(exc)})
        return

    if DANDI_FOLDER_ID not in page_text:
        errors.append({
            "stage": "DANDI_PAGE_LINK",
            "error": "Official DANDI page does not expose the expected Google Drive folder ID",
        })
        return

    drive_dir = STAGING / "dandi-drive"
    shutil.rmtree(drive_dir, ignore_errors=True)
    drive_dir.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = gdown.download_folder(
            url=DANDI_FOLDER_URL,
            output=str(drive_dir),
            quiet=False,
            use_cookies=False,
            remaining_ok=True,
        )
        (INDEX / "dandi-gdown-result.json").write_text(
            json.dumps(downloaded, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        errors.append({"stage": "DANDI_DRIVE_DOWNLOAD", "error": repr(exc)})
        return

    all_files = [path for path in drive_dir.rglob("*") if path.is_file()]
    (INDEX / "dandi-downloaded-file-list.json").write_text(
        json.dumps([str(path.relative_to(drive_dir)) for path in all_files], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    accepted_hashes: set[str] = set()
    for source in sorted(all_files):
        name_n = normalize(source.name)
        if source.suffix.lower() != ".pdf":
            continue
        if "초등" not in name_n or "디지털미디어리터러시" not in name_n:
            continue
        try:
            pages, text = verify_pdf(source, 8)
            haystack = normalize(source.name + " " + text[:20000])
            if not all(term in haystack for term in ("디지털", "미디어", "리터러시", "초등")):
                raise RuntimeError("required elementary digital media literacy title terms missing")
            file_hash = sha256(source)
            if file_hash in accepted_hashes:
                continue
            accepted_hashes.add(file_hash)
            target_name = "SRC-0046__PEN__" + safe_name(source.name)
            target = ORIGINALS / "digital-learning" / target_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            records.append({
                "source_id": "SRC-0046",
                "title": source.stem,
                "publisher": "부산광역시교육청",
                "source_page_url": DANDI_PAGE,
                "official_attachment_url": DANDI_FOLDER_URL,
                "file_name": target.name,
                "relative_path": target.relative_to(ROOT).as_posix(),
                "size_bytes": target.stat().st_size,
                "sha256": sha256(target),
                "signature": "PDF",
                "pdf_pages": pages,
                "status": "CANDIDATE_VERIFIED",
                "rights_status": "RIGHTS_UNREVIEWED",
            })
        except Exception as exc:
            errors.append({"stage": "DANDI_VERIFY", "file": source.name, "error": repr(exc)})


def main() -> int:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    acquire_sje(records, errors)
    acquire_dandi(records, errors)

    by_source: dict[str, int] = {}
    for record in records:
        by_source[record["source_id"]] = by_source.get(record["source_id"], 0) + 1

    expected_counts = {"SRC-0044": 4, "SRC-0046": 10, "SRC-0049": 4}
    count_status = {
        source_id: {
            "expected": expected,
            "actual": by_source.get(source_id, 0),
            "complete": by_source.get(source_id, 0) == expected,
        }
        for source_id, expected in expected_counts.items()
    }

    summary = {
        "verified_candidate_relations": len(records),
        "source_counts": count_status,
        "all_expected_counts_met": all(row["complete"] for row in count_status.values()),
        "errors_count": len(errors),
        "canonical_vault_promotion": "NOT_PERFORMED",
        "rights_review": "NOT_COMPLETED",
    }
    (INDEX / "candidate-originals.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (INDEX / "errors.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (INDEX / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Always return success so the audit artifact is uploaded for independent inspection.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
