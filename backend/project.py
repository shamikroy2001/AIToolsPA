"""
Task Manager with Reminder Notifications

CLI for personal tasks. Persistence is SQLite via TaskService.
Outbound Gmail reminders (SMTP) are unchanged; SMS via Twilio was removed in Phase 0.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Allow `python project.py` without an editable install.
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

from assistant.runtime import get_task_service
from assistant.services.tasks import CATEGORIES

load_dotenv()

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")


def main() -> None:
    """Main function that presents a menu to the user."""
    get_task_service()

    while True:
        print("╔══════════════════╗")
        print("║   Task Manager   ║")
        print("╠══════════════════╣")
        print("║ 1. Add Task      ║")
        print("║ 2. Remove Task   ║")
        print("║ 3. List Tasks    ║")
        print("║ 4. Modify Task   ║")
        print("║ 5. Send Reminders║")
        print("║ 6. Exit          ║")
        print("╚══════════════════╝")

        option = input("\nChoose an option: ")

        match option:
            case "1":
                add_task()
            case "2":
                remove_task()
            case "3":
                list_tasks()
            case "4":
                modify_task()
            case "5":
                send_reminder()
            case "6":
                sys.exit(0)
            case _:
                print("Invalid option.\nPlease try again.")


def add_task() -> None:
    """Adds a new task. Prompts for title, description, category, and due date."""
    title = input("Enter task title: ")
    description = input("Enter task description: ")

    print("\nSelect a category: ")
    for i, category in enumerate(CATEGORIES):
        print(f"{i + 1}. {category}")

    try:
        category_final = int(input("Choose category: ")) - 1
        if 0 <= category_final < len(CATEGORIES):
            category = CATEGORIES[category_final]
        else:
            category = "Other"
    except ValueError:
        category = "Other"

    due_date_raw = input("Enter due date (YYYY-MM-DD): ")
    try:
        due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
    except ValueError:
        print("Invalid date format.")
        return

    get_task_service().add_task(title, description, category, due_date)
    print("\nTask added successfully.")


def remove_task() -> None:
    """Removes a task by its displayed number."""
    tasks = list_tasks(return_tasks=True)

    if not tasks:
        print("No tasks to remove.")
        return

    try:
        task_number = int(input("\nEnter task number to remove: ")) - 1
        get_task_service().remove_task(task_number)
        print("\nTask removed successfully.")
    except ValueError:
        print("Invalid input.")
    except IndexError:
        print("Invalid task number.")


def list_tasks(return_tasks: bool = False):
    """
    Lists all tasks.

    :param return_tasks: If True, also return the list of task dictionaries.
    """
    service = get_task_service()
    tasks = [task.to_legacy_dict() for task in service.list_tasks()]

    if not tasks:
        print("No tasks to display.")
    else:
        print("\nList of tasks:")
        for i, task in enumerate(tasks, start=1):
            print(
                f"\nTask {i}:\nTitle: {task['title']}\n"
                f"Description: {task['description']}\n"
                f"Category: {task['category']}\n"
                f"Due date: {task['due_date']}\n"
            )

    if return_tasks:
        return tasks
    return None


def modify_task() -> None:
    """Modifies an existing task. Blank input keeps the current value."""
    tasks = list_tasks(return_tasks=True)

    if not tasks:
        print("No tasks to modify.")
        return

    try:
        task_number = int(input("\nEnter task number to modify: ")) - 1
    except ValueError:
        print("Invalid input.")
        return

    if not (0 <= task_number < len(tasks)):
        print("Invalid task number.")
        return

    task = tasks[task_number]

    print("\nModify the task details (leave blank to keep current value):")

    new_title = input(f"Enter new title [{task['title']}]: ") or task["title"]
    new_description = input(f"Enter new description [{task['description']}]: ") or task["description"]

    print("\nSelect a new category (leave blank to keep current):")
    for i, category in enumerate(CATEGORIES):
        print(f"{i + 1}. {category}")

    category = task["category"]
    try:
        category_final = input(f"Choose category [{task['category']}]: ")
        if category_final:
            category_index = int(category_final) - 1
            if 0 <= category_index < len(CATEGORIES):
                category = CATEGORIES[category_index]
    except ValueError:
        pass

    due_date = datetime.strptime(task["due_date"], "%Y-%m-%d").date()
    new_due_date = input(f"Enter new due date (YYYY-MM-DD) [{task['due_date']}]: ")
    try:
        if new_due_date:
            due_date = datetime.strptime(new_due_date, "%Y-%m-%d").date()
    except ValueError:
        print("Invalid date format, keeping current due date.")

    try:
        get_task_service().modify_task(
            task_number,
            title=new_title,
            description=new_description,
            category=category,
            due_date=due_date,
        )
        print("\nTask modified successfully.")
    except IndexError:
        print("Invalid task number.")


def send_reminder() -> None:
    """Prompts the user to send a reminder via Gmail (SMS was removed)."""
    list_tasks()

    try:
        task_num = int(input("Enter the task number to send a reminder for: ")) - 1
        task = get_task_service().get_by_index(task_num).to_legacy_dict()
    except (ValueError, IndexError):
        print("Invalid task number.")
        return

    message = f"""
    Hi there,

    This is a reminder for your upcoming task:

    Title: {task['title']}
    Description: {task['description']}
    Category: {task['category']}
    Due Date: {task['due_date']}

    Make sure to complete it on time!

    Best regards,
    Your Task Manager
    """

    option = input("Do you want an SMS or Gmail reminder? (Enter 'sms' or 'gmail'): ").strip().lower()

    if option == "sms":
        send_sms_notification(message)
    elif option == "gmail":
        send_gmail_notification(message)
    else:
        print("Invalid option. Please choose either 'sms' or 'gmail'.")


def send_sms_notification(message: str) -> None:
    """SMS via Twilio was removed in Phase 0 (cost / unused for the assistant baseline)."""
    del message
    print("SMS reminders are disabled. Twilio was removed from this project.")


def send_gmail_notification(message: str) -> None:
    """Sends an email notification using SMTP with Gmail (existing outbound reminder)."""
    while True:
        recipient_email = input("Enter the recipient's email address: ")
        if not re.search(
            r"^[a-zA-Z0-9.!#$%&'*+\/=?^_`{|}~-]+@[a-zA-Z0-9]"
            r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
            r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$",
            recipient_email,
        ):
            print("Invalid email format.\nPlease try again.")
        else:
            break

    email = EmailMessage()
    email["From"] = SENDER_EMAIL
    email["To"] = recipient_email
    email["Subject"] = "Task Reminder"
    email.set_content(message)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
            smtp.send_message(email)
        print("Email sent successfully!")
    except Exception as exc:
        print(f"Failed to send email: {str(exc)}")


if __name__ == "__main__":
    main()
