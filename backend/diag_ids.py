"""Diagnose stable_id collisions produced by the extractor over current docs."""
from __future__ import annotations

from collections import Counter
from mkc.core.database import get_session_factory
from mkc.intelligence.parsing.extractor import KnowledgeExtractor

ex = KnowledgeExtractor()
factory = get_session_factory()
with factory() as session:
    from mkc.intelligence.db_compat import get_model, model_query
    doc_model = get_model("Document")
    source_model = get_model("Source")
    docs = session.execute(model_query(doc_model)).scalars().all()
    docs = [d for d in docs if str(getattr(d, "doc_type", "")) in
            {"markdown", "code", "test", "chatgpt", "text"}]
    paths = {
        str(getattr(r, "id", "")): (str(getattr(r, "path", "") or ""),
                                    str(getattr(r, "source_type", "") or ""))
        for r in session.execute(model_query(source_model)).scalars().all()
    }
    ids: Counter = Counter()
    idinfo: dict[str, list] = {}
    for doc in docs:
        sp = paths.get(str(getattr(doc, "source_id", "")))
        if sp is None or not sp[0]:
            continue
        try:
            text = (Path(sp[0]) / str(getattr(doc, "file_path", ""))).read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            continue
        sid = str(getattr(doc, "source_id", ""))
        for obj in ex.extract_text(text, source_type=sp[1], source_id=sid,
                                   file_path=str(getattr(doc, "file_path", "")),
                                   doc_type=str(getattr(doc, "doc_type", "")),
                                   file_hash=str(getattr(doc, "file_hash", ""))):
            i = obj.stable_id()
            ids[i] += 1
            idinfo.setdefault(i, []).append(
                (obj.obj_type, obj.title[:40], str(getattr(doc, "file_path", "")),
                 obj.provenance.get("source_location")))
dups = {i: n for i, n in ids.items() if n > 1}
print("total docs:", len(docs))
print("total ids:", sum(ids.values()), "distinct:", len(ids), "dups:", len(dups))
for i, n in list(dups.items())[:8]:
    print("DUP", i, "x", n)
    for info in idinfo[i][:6]:
        print("   ", info)
from pathlib import Path
