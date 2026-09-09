from assistant.db.migrate import apply_migrations, current_version


EXPECTED_INDEXES = {
    "idx_tasks_due_date",
    "idx_tasks_status",
    "idx_tasks_category",
    "idx_tasks_created_at",
}


def test_initialize_creates_schema(conn):
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "tasks" in tables
    assert "schema_migrations" in tables


def test_schema_version(conn):
    assert current_version(conn) == 1
    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert user_version == 1


def test_migrations_are_idempotent(conn):
    apply_migrations(conn)
    apply_migrations(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    assert [row["version"] for row in rows] == [1]


def test_task_indexes_exist(conn):
    indexes = {
        row["name"]
        for row in conn.execute("PRAGMA index_list('tasks')")
    }
    assert EXPECTED_INDEXES.issubset(indexes)


def test_tasks_columns(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info('tasks')")}
    assert columns == {
        "id",
        "title",
        "description",
        "category",
        "due_date",
        "status",
        "created_at",
        "updated_at",
        "source",
    }


def test_fresh_connection_applies_migrations(tmp_path):
    from assistant.db.connection import initialize_database

    path = tmp_path / "nested" / "app.db"
    conn = initialize_database(path)
    try:
        assert path.is_file()
        assert current_version(conn) == 1
    finally:
        conn.close()


def test_apply_migrations_without_prior_table(tmp_path):
    from assistant.db.connection import connect

    path = tmp_path / "empty.db"
    conn = connect(path)
    try:
        assert current_version(conn) == 0
        version = apply_migrations(conn)
        assert version == 1
    finally:
        conn.close()
