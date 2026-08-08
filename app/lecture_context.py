import math
import re
from collections import Counter


FULL_CONTEXT_LIMIT = 34000
SELECTED_CONTEXT_LIMIT = 18000
PRIMARY_CHUNK_LIMIT = 4
EXPANDED_CONTEXT_LIMIT = 36000
EXPANDED_PRIMARY_CHUNK_LIMIT = 10
CHUNK_SIZE = 2600
CHUNK_OVERLAP = 350

STOP_WORDS = {
    "без",
    "был",
    "была",
    "были",
    "быть",
    "вопрос",
    "для",
    "его",
    "или",
    "как",
    "какие",
    "какой",
    "который",
    "может",
    "надо",
    "при",
    "такое",
    "что",
    "это",
}


def build_lecture_context(lecture_text, question, options="", strategy="focused"):
    text = (lecture_text or "").strip()
    if not text:
        return "", "none"

    if len(text) <= FULL_CONTEXT_LIMIT:
        return text, "full"

    expanded = strategy == "expanded"
    context_limit = EXPANDED_CONTEXT_LIMIT if expanded else SELECTED_CONTEXT_LIMIT
    primary_limit = EXPANDED_PRIMARY_CHUNK_LIMIT if expanded else PRIMARY_CHUNK_LIMIT
    selected_mode = "expanded" if expanded else "selected"
    truncated_mode = "expanded_truncated" if expanded else "truncated"

    chunks = split_text(text)
    query_terms = _tokenize(f"{question}\n{options}")
    if not chunks or not query_terms:
        return text[:context_limit], truncated_mode

    document_terms = [_tokenize(chunk) for chunk in chunks]
    document_frequency = Counter()
    for terms in document_terms:
        document_frequency.update(set(terms))

    scores = []
    total_documents = len(chunks)
    query_counts = Counter(query_terms)

    for index, terms in enumerate(document_terms):
        counts = Counter(terms)
        score = 0.0
        for term, query_count in query_counts.items():
            if term not in counts:
                continue
            idf = math.log((total_documents + 1) / (document_frequency[term] + 1)) + 1.0
            score += min(counts[term], 3) * idf * query_count
        scores.append((score, index))

    best = [
        index
        for score, index in sorted(scores, reverse=True)
        if score > 0
    ][:primary_limit]
    if not best:
        return text[:context_limit], truncated_mode

    # Put every strongest match before its neighbours. With a bounded context this
    # prevents an early neighbour from displacing a stronger fragment later in the file.
    selected_indices = list(best)
    for index in best:
        if index > 0:
            selected_indices.append(index - 1)
        if index + 1 < len(chunks):
            selected_indices.append(index + 1)
    selected_indices = list(dict.fromkeys(selected_indices))

    selected = []
    total_length = 0
    for index in selected_indices:
        chunk = chunks[index].strip()
        if not chunk:
            continue
        labelled = f"\n\n### Фрагмент лекции {index + 1}\n{chunk}"
        if total_length + len(labelled) > context_limit:
            break
        selected.append(labelled)
        total_length += len(labelled)

    return "".join(selected).strip(), selected_mode


def split_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|(?<=\.)\s*\n", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 <= chunk_size:
            current = f"{current}\n{paragraph}".strip()
            continue

        if current:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n{paragraph}".strip()
        else:
            start = 0
            while start < len(paragraph):
                end = start + chunk_size
                chunks.append(paragraph[start:end])
                start = max(end - overlap, start + 1)
            current = ""

    if current:
        chunks.append(current)

    return chunks


def _tokenize(text):
    words = re.findall(r"[a-zа-яё0-9]+", (text or "").lower())
    return [word for word in words if len(word) >= 3 and word not in STOP_WORDS]
