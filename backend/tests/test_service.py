from datetime import date

import pytest

from assistant.services.tasks import CATEGORIES, TaskService


def test_categories_match_original_cli():
    assert CATEGORIES == [
        "Medical Appointment",
        "Business Meeting",
        "Work Project",
        "Household Chores",
        "Study",
        "Shopping",
        "Social Events",
        "Other",
    ]


def test_add_list_remove(service: TaskService):
    service.add_task("A", "da", "Study", date(2026, 5, 1))
    service.add_task("B", "db", "Shopping", date(2026, 5, 2))
    listed = service.list_tasks()
    assert [task.title for task in listed] == ["A", "B"]

    removed = service.remove_task(0)
    assert removed.title == "A"
    assert [task.title for task in service.list_tasks()] == ["B"]


def test_remove_invalid_index(service: TaskService):
    service.add_task("A", "", "Other", date(2026, 1, 1))
    with pytest.raises(IndexError):
        service.remove_task(3)
    with pytest.raises(IndexError):
        service.remove_task(-1)


def test_modify_partial_fields(service: TaskService):
    service.add_task("Old", "desc", "Study", date(2026, 6, 1))
    updated = service.modify_task(0, title="New")
    assert updated.title == "New"
    assert updated.description == "desc"
    assert updated.due_date == date(2026, 6, 1)


def test_legacy_dict_shape(service: TaskService):
    task = service.add_task("T", "D", "Work Project", date(2026, 7, 4))
    payload = task.to_legacy_dict()
    assert set(payload.keys()) == {"title", "description", "category", "due_date"}
    assert payload["due_date"] == "2026-07-04"


def test_add_rejects_non_date(service: TaskService):
    with pytest.raises(ValueError):
        service.add_task("T", "D", "Other", "2026-01-01")  # type: ignore[arg-type]
