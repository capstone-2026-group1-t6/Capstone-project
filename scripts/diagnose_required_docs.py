"""DIAGNOSTIC ONLY -- does not write or modify anything in the project.

Answers: how many unique documents would we need to GUARANTEE are present
in the local corpus subsample, in order to fully cover every eval-eligible
question (i.e. every question that survives the same filtering
generate_eval_set_from_benchmark.py applies)?

This tells us the real size of the "required" doc set before we decide how
to build the corpus around it.

Run from repo root:
    python diagnose_required_docs.py
"""

from collections import defaultdict

from datasets import load_dataset

# Same mapping as generate_eval_set_from_benchmark.py -- kept in sync manually
QUESTION_TYPE_MAPPING = {
    "basic": ("lookup", "vector"),
    "semantic": ("lookup", "vector"),
    "intra_document_reasoning": ("cross_document", "hybrid"),
    "constrained": ("cross_document", "hybrid"),
    "conflicting_info": ("cross_document", "hybrid"),
    "completeness": ("cross_document", "hybrid"),
    "miscellaneous": ("cross_document", "hybrid"),
    "project_related": ("entity_relationship", "graph"),
}

EXCLUDED_QUESTION_TYPES = {
    "high_level",
    "info_not_found",
}


def main() -> None:
    print("Loading questions split from onyx-dot-app/EnterpriseRAG-Bench...")
    questions = load_dataset("onyx-dot-app/EnterpriseRAG-Bench", "questions")["test"]

    kept_by_strategy: dict[str, list] = defaultdict(list)
    unmapped_types_seen: set[str] = set()
    no_expected_docs = 0

    for q in questions:
        q_type = q["question_type"]
        if q_type in EXCLUDED_QUESTION_TYPES:
            continue
        if q_type not in QUESTION_TYPE_MAPPING:
            unmapped_types_seen.add(q_type)
            continue

        expected_doc_ids = q["expected_doc_ids"]
        if not expected_doc_ids:
            no_expected_docs += 1
            continue

        _, strategy = QUESTION_TYPE_MAPPING[q_type]
        kept_by_strategy[strategy].append(q)

    print(f"\nUnmapped question_type values seen (fix QUESTION_TYPE_MAPPING if non-empty): {unmapped_types_seen}")
    print(f"Questions with empty expected_doc_ids (excluded): {no_expected_docs}")

    print("\n=== Per-strategy stats ===")
    all_required_docs: set[str] = set()
    for strategy in ("vector", "hybrid", "graph"):
        qs = kept_by_strategy.get(strategy, [])
        doc_counts = [len(q["expected_doc_ids"]) for q in qs]
        strategy_docs: set[str] = set()
        for q in qs:
            strategy_docs.update(q["expected_doc_ids"])
        all_required_docs.update(strategy_docs)

        avg_docs_per_q = sum(doc_counts) / len(doc_counts) if doc_counts else 0
        max_docs_per_q = max(doc_counts) if doc_counts else 0

        print(f"\nstrategy={strategy!r}")
        print(f"  eligible questions: {len(qs)}")
        print(f"  avg expected_doc_ids per question: {avg_docs_per_q:.2f}")
        print(f"  max expected_doc_ids in a single question: {max_docs_per_q}")
        print(f"  unique documents needed to cover ALL these questions: {len(strategy_docs)}")

    print(f"\n=== Overall ===")
    print(f"Total unique documents needed to cover every eligible question (all strategies): {len(all_required_docs)}")

    single_doc_qs = 0
    multi_doc_qs = 0
    for strategy_qs in kept_by_strategy.values():
        for q in strategy_qs:
            if len(q["expected_doc_ids"]) == 1:
                single_doc_qs += 1
            else:
                multi_doc_qs += 1
    print(f"\nQuestions needing exactly 1 doc (easy to cover): {single_doc_qs}")
    print(f"Questions needing 2+ docs (all must be present together): {multi_doc_qs}")


if __name__ == "__main__":
    main()