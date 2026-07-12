from datasets import load_dataset

questions = load_dataset(
    "onyx-dot-app/EnterpriseRAG-Bench",
    "questions"
)["test"]

print(sorted(set(q["question_type"] for q in questions)))