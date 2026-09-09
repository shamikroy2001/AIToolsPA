from datetime import date
from pathlib import Path

import pytest

from assistant.csv_import import import_if_empty, import_tasks_csv


def test_import_tasks_csv(service, tmp_path: Path):
    csv_path = tmp_path / "tasks.csv"
    csv_path.write_text(
        "title,description,category,due_date\n"
        "Homework,exercises,Study,2025-04-29\n"
        "Prepare exam,Review lists,Study,2025-04-08\n",
        encoding="utf-8",
    )
    inserted = import_tasks_csv(csv_path, service)
    assert inserted == 2
    tasks = service.list_tasks()
    assert [task.title for task in tasks] == ["Homework", "Prepare exam"]
    assert tasks[0].source == "csv_import"
    assert tasks[0].due_date == date(2025, 4, 29)


def test_import_skips_blank_titles(service, tmp_path: Path):
    csv_path = tmp_path / "tasks.csv"
    csv_path.write_text(
        "title,description,category,due_date\n"
        ",oops,Study,2025-01-01\n"
        "Keep me,ok,Study,2025-01-02\n",
        encoding="utf-8",
    )
    assert import_tasks_csv(csv_path, service) == 1
    assert service.list_tasks()[0].title == "Keep me"


def test_import_if_empty_runs_once(service, tmp_path: Path):
    csv_path = tmp_path / "tasks.csv"
    csv_path.write_text(
        "title,description,category,due_date\n"
        "Only,once,Study,2025-01-01\n",
        encoding="utf-8",
    )
    assert import_if_empty(csv_path, service) == 1
    assert import_if_empty(csv_path, service) == 0
    assert service.count() == 1


def test_import_missing_file(service, tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        import_tasks_csv(tmp_path / "missing.csv", service)


def test_import_real_tasks_csv_if_present(service):
    """Regression: the cloned tasks.csv must still load."""
    root_csv = Path(__file__).resolve().parents[2] / "tasks.csv"
    if not root_csv.is_file():
        pytest.skip("tasks.csv not in repository root")
    inserted = import_tasks_csv(root_csv, service)
    assert inserted >= 1
    assert service.count() == inserted
