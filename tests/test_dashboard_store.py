from pathlib import Path

import pytest

from app.models.dashboard import DashboardDefinition, DashboardLayout, DashboardPanel
from app.services.dashboard_store import DashboardStore


def sample_dashboard(title="보안 현황"):
    return DashboardDefinition(
        title=title, description="test", panels=[DashboardPanel(
            id="p1", title="이벤트", description="count", visualization="metric",
            query="table duration=24h events | stats count", layout=DashboardLayout(x=0, y=0, width=6, height=4),
        )],
    )


def test_dashboard_lifecycle_and_revisions(tmp_path: Path):
    store = DashboardStore(tmp_path / "dashboards.db")
    first = store.save(sample_dashboard(), change_note="created")
    assert first.revision == 1
    assert store.list()[0].panel_count == 1

    changed = sample_dashboard("변경된 보안 현황")
    second = store.save(changed, first.id, "renamed")
    assert second.revision == 2
    assert [item["revision"] for item in store.revisions(first.id)] == [2, 1]
    assert "변경된 보안 현황" in store.diff(first.id, 1, 2)

    restored = store.restore(first.id, 1, "rollback")
    assert restored.revision == 3
    assert restored.dashboard.title == "보안 현황"

    clone = store.clone(first.id)
    assert clone.id != first.id
    assert clone.dashboard.title.endswith("복사본")

    store.delete(first.id)
    with pytest.raises(KeyError):
        store.get(first.id)
