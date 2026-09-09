from datetime import date, timedelta

import pytest

from assistant.models import Task, new_id, utc_now


def test_add_and_get(repo):
    now = utc_now()
    created = repo.add(
        Task(
            id=new_id(),
            title="Alpha",
            description="First",
            category="Study",
            due_date=date(2026, 1, 15),
            created_at=now,
            updated_at=now,
        )
    )
    loaded = repo.get(created.id)
    assert loaded is not None
    assert loaded.title == "Alpha"
    assert loaded.due_date == date(2026, 1, 15)
    assert loaded.status == "open"
    assert loaded.source == "user"


def test_list_order_is_insertion_order(repo):
    first = utc_now()
    second = first + timedelta(seconds=1)
    repo.add(
        Task(
            id=new_id(),
            title="First",
            description="",
            category="Other",
            due_date=date(2026, 1, 1),
            created_at=first,
            updated_at=first,
        )
    )
    repo.add(
        Task(
            id=new_id(),
            title="Second",
            description="",
            category="Other",
            due_date=date(2026, 1, 2),
            created_at=second,
            updated_at=second,
        )
    )
    titles = [task.title for task in repo.list_all()]
    assert titles == ["First", "Second"]


def test_update_and_delete(repo):
    task = repo.add(
        Task(
            id=new_id(),
            title="Old",
            description="d",
            category="Study",
            due_date=date(2026, 2, 1),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    task.title = "New"
    updated = repo.update(task)
    assert updated.title == "New"
    assert repo.get(task.id).title == "New"

    assert repo.delete(task.id) is True
    assert repo.get(task.id) is None
    assert repo.delete(task.id) is False


def test_update_missing_raises(repo):
    missing = Task(
        id=new_id(),
        title="Gone",
        description="",
        category="Other",
        due_date=date(2026, 1, 1),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    with pytest.raises(KeyError):
        repo.update(missing)


def test_count(repo):
    assert repo.count() == 0
    repo.add(
        Task(
            id=new_id(),
            title="One",
            description="",
            category="Other",
            due_date=date(2026, 3, 1),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    assert repo.count() == 1
