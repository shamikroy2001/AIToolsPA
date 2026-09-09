"""Task use cases. CLI and CSV import call this layer, not SQLite directly."""

from __future__ import annotations

from datetime import date

from assistant.models import Task, new_id, utc_now
from assistant.repositories.tasks import TaskRepository

CATEGORIES = [
    "Medical Appointment",
    "Business Meeting",
    "Work Project",
    "Household Chores",
    "Study",
    "Shopping",
    "Social Events",
    "Other",
]


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def add_task(
        self,
        title: str,
        description: str,
        category: str,
        due_date: date,
        *,
        source: str = "user",
        status: str = "open",
    ) -> Task:
        title = title.strip()
        if not isinstance(due_date, date):
            raise ValueError("due_date must be a date.")
        now = utc_now()
        task = Task(
            id=new_id(),
            title=title,
            description=description.strip(),
            category=category.strip() or "Other",
            due_date=due_date,
            status=status,
            created_at=now,
            updated_at=now,
            source=source,
        )
        return self._repository.add(task)

    def list_tasks(self) -> list[Task]:
        return self._repository.list_all()

    def count(self) -> int:
        return self._repository.count()

    def is_empty(self) -> bool:
        return self.count() == 0

    def get_by_index(self, index: int) -> Task:
        """0-based index in list order. Raises IndexError if out of range."""
        tasks = self.list_tasks()
        if index < 0 or index >= len(tasks):
            raise IndexError("Invalid task number.")
        return tasks[index]

    def remove_task(self, index: int) -> Task:
        task = self.get_by_index(index)
        self._repository.delete(task.id)
        return task

    def modify_task(
        self,
        index: int,
        *,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        due_date: date | None = None,
    ) -> Task:
        task = self.get_by_index(index)
        if title is not None:
            task.title = title.strip()
        if description is not None:
            task.description = description.strip()
        if category is not None:
            task.category = category.strip() or task.category
        if due_date is not None:
            task.due_date = due_date
        return self._repository.update(task)
