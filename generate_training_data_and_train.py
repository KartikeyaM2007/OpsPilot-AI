from pathlib import Path
import sys
import random

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
DATA_DIR = ROOT / "data"

sys.path.insert(0, str(BACKEND_DIR))

from app.agentic_assignment_engine import assign_task_agentic
from app.ml_ranking_model import append_candidate_training_rows, train_ml_model, get_ml_status


TRAINING_PATH = DATA_DIR / "ml_training_candidates.csv"


TASK_BANK = [
    {
        "task_id": "TRAIN-PAY-001",
        "title": "Customer payment failed after card checkout",
        "description": "Customer says payment failed after checkout using card and amount was debited.",
        "priority": "high",
        "category": "payment",
        "required_skills": ["payments", "billing", "customer_support"],
        "sla_minutes": 60,
    },
    {
        "task_id": "TRAIN-PAY-002",
        "title": "UPI payment stuck in pending state",
        "description": "UPI transaction is pending and customer cannot complete order.",
        "priority": "urgent",
        "category": "payment",
        "required_skills": ["payments", "billing", "customer_support"],
        "sla_minutes": 45,
    },
    {
        "task_id": "TRAIN-BILL-001",
        "title": "Refund request for duplicate charge",
        "description": "Customer was charged twice and wants an urgent refund.",
        "priority": "high",
        "category": "billing",
        "required_skills": ["billing", "refunds", "customer_support"],
        "sla_minutes": 60,
    },
    {
        "task_id": "TRAIN-BILL-002",
        "title": "Subscription invoice amount is incorrect",
        "description": "Customer says the invoice amount does not match the selected plan.",
        "priority": "medium",
        "category": "billing",
        "required_skills": ["billing", "customer_support"],
        "sla_minutes": 180,
    },
    {
        "task_id": "TRAIN-TECH-001",
        "title": "Partner API latency issue",
        "description": "Partner reports API response is slow and sometimes timing out.",
        "priority": "urgent",
        "category": "technical",
        "required_skills": ["technical_support", "api", "debugging"],
        "sla_minutes": 45,
    },
    {
        "task_id": "TRAIN-TECH-002",
        "title": "Production server error during login",
        "description": "Users are seeing server error and timeout during login.",
        "priority": "urgent",
        "category": "technical",
        "required_skills": ["technical_support", "api", "debugging"],
        "sla_minutes": 30,
    },
    {
        "task_id": "TRAIN-ACC-001",
        "title": "User account locked",
        "description": "Customer cannot login because account is locked after multiple attempts.",
        "priority": "medium",
        "category": "account",
        "required_skills": ["account_management", "customer_support"],
        "sla_minutes": 120,
    },
    {
        "task_id": "TRAIN-ACC-002",
        "title": "Password reset not working",
        "description": "User requested password reset but did not receive the reset link.",
        "priority": "medium",
        "category": "account",
        "required_skills": ["account_management", "customer_support"],
        "sla_minutes": 120,
    },
    {
        "task_id": "TRAIN-GEN-001",
        "title": "General dashboard usage question",
        "description": "Customer wants help understanding the analytics dashboard.",
        "priority": "low",
        "category": "general",
        "required_skills": ["customer_support"],
        "sla_minutes": 240,
    },
    {
        "task_id": "TRAIN-GEN-002",
        "title": "Product information request",
        "description": "Customer wants information about plan features and dashboard options.",
        "priority": "low",
        "category": "general",
        "required_skills": ["customer_support"],
        "sla_minutes": 240,
    },
]


TIME_VARIANTS = [
    "09:30",
    "10:30",
    "12:15",
    "15:00",
    "17:30",
]


def reset_training_file():
    if TRAINING_PATH.exists():
        backup = TRAINING_PATH.with_suffix(".backup.csv")
        backup.write_text(TRAINING_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        TRAINING_PATH.unlink()
        print(f"Backed up old training file to: {backup}")


def generate_training_data(repetitions: int = 4):
    rows_written = 0
    assignments_created = 0

    for round_index in range(repetitions):
        random.shuffle(TASK_BANK)

        for task_index, task in enumerate(TASK_BANK):
            now_hhmm = TIME_VARIANTS[(task_index + round_index) % len(TIME_VARIANTS)]

            task_payload = dict(task)
            task_payload["task_id"] = f"{task['task_id']}-R{round_index + 1}"

            result = assign_task_agentic(task_payload, now_hhmm=now_hhmm)
            written = append_candidate_training_rows(result)

            rows_written += written
            assignments_created += 1

            assigned = result.get("assigned_resource") or {}
            print(
                f"[{assignments_created:02d}] {task_payload['title']} "
                f"at {now_hhmm} -> {assigned.get('name', 'Unassigned')} "
                f"({written} candidate rows)"
            )

    return {
        "assignments_created": assignments_created,
        "candidate_rows_written": rows_written,
    }


def main():
    print("Generating synthetic candidate-level training data...")
    print("This will train the ML ranker using Agentic RAG decisions as labels.")
    print()

    reset_training_file()

    summary = generate_training_data(repetitions=5)

    print()
    print("Training data generation complete.")
    print(f"Assignments created: {summary['assignments_created']}")
    print(f"Candidate rows written: {summary['candidate_rows_written']}")
    print()

    print("Training ML ranker...")
    train_result = train_ml_model()

    print(train_result.get("message"))

    status = get_ml_status()
    print()
    print("ML status:")
    print(f"Model exists: {status['model_exists']}")
    print(f"Training rows: {status['training_rows']}")
    print(f"Positive rows: {status['positive_rows']}")
    print(f"Negative rows: {status['negative_rows']}")

    metadata = status.get("metadata") or {}
    if metadata:
        print(f"Training accuracy: {metadata.get('train_accuracy')}")
        print("Top features:")
        for item in metadata.get("top_features", []):
            print(f"  - {item['feature']}: {item['importance']}")

    print()
    print("Done. Refresh the frontend and click ML Ranker Assignment.")


if __name__ == "__main__":
    main()
