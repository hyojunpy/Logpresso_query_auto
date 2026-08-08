import sqlite3

from app.models.request import FeedbackRequest
from app.services.feedback_store import FeedbackStore


def test_improvement_report_uses_metadata_not_raw_request_text(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.db")
    store.save(FeedbackRequest(request_text="password=secret", result_status="generated", rating="negative", issue_type="wrong_field"))
    report = store.improvement_report()
    assert report["total_feedback"] == 1
    assert report["priority_issue_types"] == ["wrong_field"]


def test_masks_common_personal_and_credential_values_in_stored_comment(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.db")
    saved = store.save(FeedbackRequest(
        request_text="request", result_status="generated", rating="negative", store_raw_text=True,
        feedback_comment="contact user@example.com from 192.168.10.5 bearer abc.def_123",
    ))
    assert saved["raw_text_stored"] is True
    with sqlite3.connect(tmp_path / "feedback.db") as conn:
        comment = conn.execute("select feedback_comment from query_feedback").fetchone()[0]
    assert comment == "contact [EMAIL] from [IP] Bearer [REDACTED]"


def test_records_only_hashed_unsuccessful_generation_outcomes(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.db")
    store.record_generation_outcome("internal request", "needs_clarification")
    store.record_generation_outcome("successful request", "generated")

    report = store.improvement_report()

    assert report["unresolved_outcomes"] == {"needs_clarification": 1}
    with sqlite3.connect(tmp_path / "feedback.db") as conn:
        assert conn.execute("select request_hash, result_status from generation_outcome").fetchall()[0][1] == "needs_clarification"
