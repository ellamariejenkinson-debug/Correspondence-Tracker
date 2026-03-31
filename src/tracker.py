#!/usr/bin/env python3
"""Correspondence Tracker for disputes lawyers.

Functions:
- add new letter text/filename
- extract date/from/to/themes
- store in SQLite
- show and search with cross-reference similarities
"""

import argparse
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).resolve().parents[0] / ".." / "data" / "correspondence.db"
STOPWORDS = {
    "the", "and", "of", "to", "a", "in", "for", "on", "with", "is", "are", "that", "this",
    "by", "from", "at", "be", "as", "it", "or", "an", "was", "will", "not", "have", "has",
    "you", "your", "we", "our", "us", "but", "if", "they", "their", "them", "these", "those",
    "letter", "correspondence", "regards", "sir", "madam"
}

SIMILARITY_TOP_K = 3


def local_print(*args, **kwargs):
    print(*args, **kwargs)


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS letters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        received_at TEXT,
        from_party TEXT,
        to_party TEXT,
        issue_date TEXT,
        summary TEXT,
        themes TEXT,
        content TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def extract_metadata(content: str, override_from: Optional[str] = None, override_to: Optional[str] = None,
                     override_issue_date: Optional[str] = None) -> Dict[str, Optional[str]]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    metadata = {
        "from_party": override_from,
        "to_party": override_to,
        "issue_date": override_issue_date,
    }

    if metadata["from_party"] is None:
        for line in lines[:20]:
            m = re.match(r"^(From|Sender|Issued by)\s*[:\-]\s*(.+)$", line, re.I)
            if m:
                metadata["from_party"] = m.group(2).strip()
                break

    if metadata["to_party"] is None:
        for line in lines[:20]:
            m = re.match(r"^(To|Recipient|Addressed to)\s*[:\-]\s*(.+)$", line, re.I)
            if m:
                metadata["to_party"] = m.group(2).strip()
                break

    if metadata["from_party"] is None and lines:
        for line in lines[:20]:
            m = re.match(r"^Dear\s+(.+)$", line, re.I)
            if m:
                metadata["to_party"] = metadata["to_party"] or m.group(1).strip()
                break

    if metadata["issue_date"] is None:
        for line in lines[:40]:
            m = re.search(r"(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4}|\d{4}[\-/]\d{1,2}[\-/]\d{1,2})", line)
            if m:
                metadata["issue_date"] = m.group(1)
                break
        if metadata["issue_date"] is None:
            for line in lines[:40]:
                m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
                              line, re.I)
                if m:
                    metadata["issue_date"] = m.group(0)
                    break

    return metadata


def extract_themes(content: str, top_n: int = 10) -> List[str]:
    text = re.sub(r"[^A-Za-z0-9 '\-]", " ", content).lower()
    tokens = [w for w in text.split() if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]
    freq = Counter(tokens)
    return [w for w, _ in freq.most_common(top_n)]


def insert_letter(content: str, from_party: Optional[str], to_party: Optional[str], issue_date: Optional[str]):
    parsed = extract_metadata(content, from_party, to_party, issue_date)
    themes = extract_themes(content)
    summary = "; ".join(themes[:5])

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    created_at = datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO letters (created_at, received_at, from_party, to_party, issue_date, summary, themes, content) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (created_at, datetime.utcnow().date().isoformat(), parsed.get("from_party"), parsed.get("to_party"),
         parsed.get("issue_date"), summary, ", ".join(themes), content)
    )
    conn.commit()
    letter_id = c.lastrowid
    conn.close()
    return letter_id


def fetch_letters() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, created_at, received_at, from_party, to_party, issue_date, summary, themes, content FROM letters ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(zip(["id", "created_at", "received_at", "from_party", "to_party", "issue_date", "summary", "themes", "content"], row)) for row in rows]


def get_letter(letter_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, created_at, received_at, from_party, to_party, issue_date, summary, themes, content FROM letters WHERE id = ?", (letter_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(zip(["id", "created_at", "received_at", "from_party", "to_party", "issue_date", "summary", "themes", "content"], row))
    return None


def search_letters(from_party: Optional[str] = None, to_party: Optional[str] = None,
                   issue_date_from: Optional[str] = None, issue_date_to: Optional[str] = None,
                   theme: Optional[str] = None, query: Optional[str] = None) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    sql = "SELECT id, created_at, received_at, from_party, to_party, issue_date, summary, themes, content FROM letters WHERE 1=1"
    params: List[str] = []

    if from_party:
        sql += " AND lower(from_party) LIKE lower(?)"
        params.append(f"%{from_party}%")

    if to_party:
        sql += " AND lower(to_party) LIKE lower(?)"
        params.append(f"%{to_party}%")

    if issue_date_from:
        sql += " AND date(issue_date) >= date(?)"
        params.append(issue_date_from)

    if issue_date_to:
        sql += " AND date(issue_date) <= date(?)"
        params.append(issue_date_to)

    if theme:
        sql += " AND lower(themes) LIKE lower(?)"
        params.append(f"%{theme}%")

    if query:
        sql += " AND (lower(content) LIKE lower(?) OR lower(summary) LIKE lower(?) OR lower(themes) LIKE lower(?))"
        q = f"%{query}%"
        params.extend([q, q, q])

    sql += " ORDER BY id DESC"
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [dict(zip(["id", "created_at", "received_at", "from_party", "to_party", "issue_date", "summary", "themes", "content"], row)) for row in rows]


def cosine_sim(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def vectorize_texts(texts: List[str]) -> List[Dict[str, float]]:
    # simple term frequency vectors
    documents = []
    vocabulary = Counter()
    for text in texts:
        tokens = [tok for tok in re.sub(r"[^a-z0-9 ]", " ", text.lower()).split() if len(tok) > 2 and tok not in STOPWORDS]
        doc_freq = Counter(tokens)
        documents.append(doc_freq)
        vocabulary.update(doc_freq.keys())

    vocab_list = list(vocabulary.keys())
    word_index = {w: i for i, w in enumerate(vocab_list)}

    vectors = []
    for doc_freq in documents:
        vec = [0.0] * len(vocab_list)
        total = sum(doc_freq.values())
        if total > 0:
            for word, count in doc_freq.items():
                if word in word_index:
                    vec[word_index[word]] = count / total
        vectors.append(vec)
    return vectors


def find_related(letter_id: int, top_k: int = SIMILARITY_TOP_K) -> List[Tuple[int, float]]:
    letters = fetch_letters()
    if not letters:
        return []
    target = next((l for l in letters if l["id"] == letter_id), None)
    if not target:
        return []
    contents = [l["content"] for l in letters]
    vectors = vectorize_texts(contents)
    idx = next(i for i, l in enumerate(letters) if l["id"] == letter_id)
    base = vectors[idx]
    scores = []
    for i, vec in enumerate(vectors):
        if i == idx:
            continue
        scores.append((letters[i]["id"], cosine_sim(base, vec)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


def print_letter(letter: Dict):
    local_print("---")
    local_print(f"ID: {letter['id']}")
    local_print(f"Created at: {letter['created_at']}")
    local_print(f"Received at: {letter['received_at']}")
    local_print(f"From: {letter.get('from_party') or 'N/A'}")
    local_print(f"To: {letter.get('to_party') or 'N/A'}")
    local_print(f"Issue date: {letter.get('issue_date') or 'N/A'}")
    local_print(f"Summary: {letter.get('summary') or 'N/A'}")
    local_print(f"Themes: {letter.get('themes') or 'N/A'}")
    local_print("Content:")
    local_print(letter["content"][:800] + ("..." if len(letter["content"]) > 800 else ""))


def handle_add(args):
    if args.file:
        if not os.path.exists(args.file):
            local_print(f"File not found: {args.file}")
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    elif args.content:
        content = args.content
    else:
        local_print("Error: either --file or --content must be provided")
        sys.exit(1)

    content = normalize_text(content)
    letter_id = insert_letter(content, args.from_party, args.to_party, args.issue_date)
    local_print(f"Added letter with ID {letter_id}")

    related = find_related(letter_id)
    if related:
        local_print("Related letters (sorted by content similarity):")
        for rid, score in related:
            local_print(f"- ID {rid}, score {score:.4f}")
    else:
        local_print("No related letters found.")


def handle_list(_args):
    letters = search_letters()
    if not letters:
        local_print("No letters stored.")
        return
    for l in letters:
        local_print(f"{l['id']}: {l['from_party'] or 'Unknown'} -> {l['to_party'] or 'Unknown'}; {l['issue_date'] or 'No date'}; themes: {l['themes']}")


def handle_search(args):
    letters = search_letters(
        from_party=args.from_party,
        to_party=args.to_party,
        issue_date_from=args.issue_date_from,
        issue_date_to=args.issue_date_to,
        theme=args.theme,
        query=args.query
    )
    if not letters:
        local_print("No letters match the filter criteria.")
        return
    for l in letters:
        local_print(f"{l['id']}: {l['from_party'] or 'Unknown'} -> {l['to_party'] or 'Unknown'}; {l['issue_date'] or 'No date'}; themes: {l['themes']}")


def handle_view(args):
    letter = get_letter(args.id)
    if not letter:
        local_print(f"No letter with ID {args.id}")
        return
    print_letter(letter)
    related = find_related(args.id)
    if related:
        local_print("\nCross-referenced similar letters:")
        for rid, score in related:
            part = get_letter(rid)
            local_print(f"- ID {rid}, score {score:.4f}, from {part['from_party'] or 'N/A'} to {part['to_party'] or 'N/A'}")


def main():
    init_db()
    parser = argparse.ArgumentParser(description="Correspondence Tracker")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="Add correspondence")
    p_add.add_argument("--file", help="Text file containing the letter")
    p_add.add_argument("--content", help="Letter text content (alternatively to --file)")
    p_add.add_argument("--from", dest="from_party", help="Override from party")
    p_add.add_argument("--to", dest="to_party", help="Override to party")
    p_add.add_argument("--date", dest="issue_date", help="Override issue date")
    p_add.set_defaults(func=handle_add)

    p_list = sub.add_parser("list", help="List letters")
    p_list.set_defaults(func=handle_list)

    p_view = sub.add_parser("view", help="View details of letter")
    p_view.add_argument("id", type=int, help="Letter ID")
    p_view.set_defaults(func=handle_view)

    p_search = sub.add_parser("search", help="Search letters by filters")
    p_search.add_argument("--from", dest="from_party", help="Filter by from party")
    p_search.add_argument("--to", dest="to_party", help="Filter by to party")
    p_search.add_argument("--issue-date-from", dest="issue_date_from", help="Filter by minimum issue date (YYYY-MM-DD)")
    p_search.add_argument("--issue-date-to", dest="issue_date_to", help="Filter by maximum issue date (YYYY-MM-DD)")
    p_search.add_argument("--theme", help="Filter by theme keyword")
    p_search.add_argument("--query", help="Full text query in content/summary/themes")
    p_search.set_defaults(func=handle_search)

    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
