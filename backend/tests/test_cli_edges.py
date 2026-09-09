"""CLI edge cases that the original CSV tests did not cover."""

from project import add_task, list_tasks, modify_task, remove_task, send_sms_notification


def test_add_task_invalid_date_does_not_insert(isolated_cli, monkeypatch):
    answers = iter(["Title", "Desc", "1", "not-a-date"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    add_task()
    assert isolated_cli.count() == 1


def test_add_task_invalid_category_becomes_other(isolated_cli, monkeypatch):
    answers = iter(["Title", "Desc", "99", "2026-01-01"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    add_task()
    assert isolated_cli.list_tasks()[-1].category == "Other"


def test_remove_invalid_number(isolated_cli, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "9")
    remove_task()
    captured = capsys.readouterr().out
    assert "Invalid task number." in captured
    assert isolated_cli.count() == 1


def test_list_empty(service, monkeypatch, capsys):
    from assistant.runtime import reset_runtime, set_task_service

    reset_runtime()
    set_task_service(service)
    try:
        result = list_tasks(return_tasks=True)
        assert result == []
        assert "No tasks to display." in capsys.readouterr().out
    finally:
        reset_runtime()


def test_modify_invalid_input(isolated_cli, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "nope")
    modify_task()
    assert "Invalid input." in capsys.readouterr().out


def test_sms_disabled(capsys):
    send_sms_notification("hello")
    assert "SMS reminders are disabled" in capsys.readouterr().out
