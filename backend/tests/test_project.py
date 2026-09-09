"""CLI-level tests. Names from the original test_project.py are preserved."""

from datetime import date

from project import add_task, list_tasks, modify_task, remove_task


def test_add_task(isolated_cli, monkeypatch):
    """Tests if a task is correctly added."""
    answers = iter(["New Task", "New Desc", "5", "2024-10-10"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    add_task()
    tasks = isolated_cli.list_tasks()

    assert len(tasks) == 2
    assert tasks[1].title == "New Task"
    assert tasks[1].description == "New Desc"
    assert tasks[1].category == "Study"
    assert tasks[1].due_date == date(2024, 10, 10)


def test_remove_task(isolated_cli, monkeypatch):
    """Tests if a task is correctly removed."""
    assert isolated_cli.count() == 1
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")

    remove_task()

    assert isolated_cli.count() == 0


def test_list_tasks(isolated_cli):
    """Tests if listing tasks returns the correct number of tasks."""
    tasks = list_tasks(return_tasks=True)

    assert len(tasks) == 1
    assert tasks[0]["title"] == "Test Task"
    assert tasks[0]["description"] == "Test Desc"
    assert tasks[0]["category"] == "Work"
    assert tasks[0]["due_date"] == "2024-09-30"


def test_modify_task(isolated_cli, monkeypatch):
    """Tests if modifying a task updates the correct details."""
    answers = iter(["1", "Updated Task", "Updated Desc", "", ""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    modify_task()
    tasks = isolated_cli.list_tasks()

    assert tasks[0].title == "Updated Task"
    assert tasks[0].description == "Updated Desc"
    assert tasks[0].category == "Work"
    assert tasks[0].due_date == date(2024, 9, 30)
