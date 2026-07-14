"""Hand-crafted graph eval questions from data/seed/graph_seed.json.

Fills the graph slice of the held-out set to meet the Evaluation plan target
of >= 50 examples per strategy (vector / hybrid / graph).

Questions are entity-relationship queries answerable from Neo4j seed facts
(reports_to, owns, works_on, collaborates_with, person titles). Only
relationships that actually land in Neo4j under scripts/build_graph_index.py
are used (owns/works_on require the project to exist in graph_seed.projects).

Appends new rows to data/eval_set.jsonl. Does not remove existing examples.
Re-run is idempotent for rows with question_id prefix qst_graph_seed_.

Team should spot-check a sample before treating as final hand-validation.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED_PATH = REPO / "data" / "seed" / "graph_seed.json"
EVAL_PATH = REPO / "data" / "eval_set.jsonl"
ID_PREFIX = "qst_graph_seed_"
TARGET_GRAPH = 50


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _fact_ids(*parts: str) -> list[str]:
    """Stable gold citation keys for graph facts (for human review + soft match)."""
    key = "_".join(p.replace(" ", "_") for p in parts)
    return [key, f"graph:{key}"]


def build_candidates(seed: dict) -> list[dict]:
    projects = {p["name"] for p in seed.get("projects", [])}
    people = {p["name"]: (p.get("title") or "").strip() for p in seed.get("people", [])}
    candidates: list[dict] = []

    def add(
        question: str,
        expected_answer: str,
        source_chunk_ids: list[str],
        *,
        kind: str,
    ) -> None:
        candidates.append(
            {
                "question": question,
                "expected_answer": expected_answer,
                "expected_strategy": "graph",
                "query_pattern": "entity_relationship",
                "source_chunk_ids": source_chunk_ids,
                "question_type": "graph_org_seed",
                "graph_fact_kind": kind,
            }
        )

    # --- REPORTS_TO ---
    for rel in seed.get("reports_to", []):
        person, manager = rel["person"], rel["manager"]
        if person not in people or manager not in people:
            continue
        ids = _fact_ids("reports_to", person, manager)
        add(
            f"Who does {person} report to?",
            f"{person} reports to {manager}.",
            ids,
            kind="reports_to",
        )
        add(
            f"Who is the manager of {person}?",
            f"The manager of {person} is {manager}.",
            ids,
            kind="reports_to",
        )

    # Reverse: who reports to manager X?
    reports_to_manager: dict[str, list[str]] = {}
    for rel in seed.get("reports_to", []):
        reports_to_manager.setdefault(rel["manager"], []).append(rel["person"])
    for manager, reports in sorted(reports_to_manager.items()):
        if manager not in people:
            continue
        reports = sorted(reports)
        ids = []
        for p in reports:
            ids.extend(_fact_ids("reports_to", p, manager))
        names = ", ".join(reports)
        add(
            f"Who reports to {manager}?",
            f"The following people report to {manager}: {names}.",
            ids,
            kind="reports_to",
        )

    # --- OWNS (project must exist in projects list for Neo4j seed) ---
    for rel in seed.get("owns", []):
        person, project = rel["person"], rel["project"]
        if person not in people or project not in projects:
            continue
        ids = _fact_ids("owns", person, project)
        add(
            f"Who owns the {project} project?",
            f"{person} owns the {project} project.",
            ids,
            kind="owns",
        )
        add(
            f"What project does {person} own?",
            f"{person} owns {project}.",
            ids,
            kind="owns",
        )

    # --- WORKS_ON ---
    works_on_project: dict[str, list[str]] = {}
    for rel in seed.get("works_on", []):
        person, project = rel["person"], rel["project"]
        if person not in people or project not in projects:
            continue
        works_on_project.setdefault(project, []).append(person)
        ids = _fact_ids("works_on", person, project)
        add(
            f"Does {person} work on {project}?",
            f"Yes. {person} works on {project}.",
            ids,
            kind="works_on",
        )

    for project, members in sorted(works_on_project.items()):
        members = sorted(set(members))
        ids = []
        for p in members:
            ids.extend(_fact_ids("works_on", p, project))
        add(
            f"Who works on the {project} project?",
            f"People who work on {project}: {', '.join(members)}.",
            ids,
            kind="works_on",
        )

    # --- COLLABORATES_WITH ---
    for rel in seed.get("collaborates_with", []):
        a, b = rel["person_a"], rel["person_b"]
        if a not in people or b not in people:
            continue
        lo, hi = sorted([a, b])
        ids = _fact_ids("collaborates_with", lo, hi)
        add(
            f"Who does {a} collaborate with among known org-chart pairs involving them?",
            f"{a} collaborates with {b}.",
            ids,
            kind="collaborates_with",
        )
        add(
            f"Do {a} and {b} collaborate?",
            f"Yes. {a} and {b} collaborate with each other.",
            ids,
            kind="collaborates_with",
        )

    # --- TITLES ---
    for name, title in people.items():
        if not title:
            continue
        ids = _fact_ids("title", name)
        add(
            f"What is {name}'s title?",
            f"{name}'s title is {title}.",
            ids,
            kind="title",
        )
        # Role-style reverse only when title is distinctive enough
        if len(title) >= 12:
            add(
                f"Who has the title {title}?",
                f"{name} has the title {title}.",
                ids,
                kind="title",
            )

    return candidates


def main() -> None:
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    existing = _load_jsonl(EVAL_PATH)
    graph_rows = [r for r in existing if r.get("expected_strategy") == "graph"]
    n_graph = len(graph_rows)
    print(f"Existing graph examples: {n_graph}")

    existing_ids = {r.get("question_id") for r in existing if r.get("question_id")}
    existing_questions = {r.get("question", "").strip().lower() for r in existing}

    # Drop prior auto-generated seed rows so re-run is clean
    kept = [r for r in existing if not str(r.get("question_id", "")).startswith(ID_PREFIX)]
    n_graph_kept = sum(1 for r in kept if r.get("expected_strategy") == "graph")
    print(f"Graph examples kept (non-{ID_PREFIX}*): {n_graph_kept}")

    need = max(0, TARGET_GRAPH - n_graph_kept)
    print(f"Need {need} more graph examples to reach {TARGET_GRAPH}.")

    candidates = build_candidates(seed)
    # Prefer relationship queries over titles for diversity
    kind_order = {
        "reports_to": 0,
        "owns": 1,
        "works_on": 2,
        "collaborates_with": 3,
        "title": 4,
    }
    candidates.sort(key=lambda r: (kind_order.get(r.get("graph_fact_kind", ""), 9), r["question"]))

    selected: list[dict] = []
    used_questions: set[str] = set()
    idx = 1
    for cand in candidates:
        if len(selected) >= need:
            break
        qnorm = cand["question"].strip().lower()
        if qnorm in existing_questions or qnorm in used_questions:
            continue
        qid = f"{ID_PREFIX}{idx:04d}"
        while qid in existing_ids:
            idx += 1
            qid = f"{ID_PREFIX}{idx:04d}"
        row = {
            "question": cand["question"],
            "expected_answer": cand["expected_answer"],
            "expected_strategy": "graph",
            "query_pattern": "entity_relationship",
            "source_chunk_ids": cand["source_chunk_ids"],
            "question_id": qid,
            "question_type": cand["question_type"],
        }
        selected.append(row)
        used_questions.add(qnorm)
        existing_ids.add(qid)
        idx += 1

    if len(selected) < need:
        print(
            f"WARNING: only generated {len(selected)} new graph examples "
            f"(requested {need}). Graph seed may be too small."
        )

    out_rows = kept + selected
    EVAL_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n",
        encoding="utf-8",
    )

    from collections import Counter

    counts = Counter(r["expected_strategy"] for r in out_rows)
    print(f"Wrote {len(selected)} new graph rows to {EVAL_PATH}")
    print(f"Eval set strategy counts: {dict(counts)}")
    print(f"Total examples: {len(out_rows)}")
    if counts.get("graph", 0) >= TARGET_GRAPH:
        print(f"Graph target met: {counts['graph']} >= {TARGET_GRAPH}")
    else:
        print(f"Graph target NOT met: {counts.get('graph', 0)} < {TARGET_GRAPH}")


if __name__ == "__main__":
    main()
