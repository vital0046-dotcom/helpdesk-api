import json

from helpdesk import create_app
from tools.analyze_logs import nested_counts, optimized_counts, read_logs


def test_analyzers_match_and_skip_bad_lines(tmp_path):
    path = tmp_path / "requests.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"path":"/a","status":200}',
                '{"path":"/a","status":404}',
                '{"path":"/b","status":500}',
                "broken",
                "{}",
                "[]",
            ]
        ),
        encoding="utf-8",
    )
    rows, skipped = read_logs(path)
    assert skipped == 3
    assert nested_counts(rows) == optimized_counts(rows) == {"/a": 2, "/b": 1}
    assert nested_counts([]) == optimized_counts([]) == {}


def test_access_log_excludes_secrets(tmp_path):
    path = tmp_path / "requests.jsonl"
    app = create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "LOG_FILE": str(path),
            "API_KEY": "secret",
        }
    )
    app.test_client().get("/api/tickets?private=hidden", headers={"X-API-Key": "wrong"})
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["status"] == 401
    assert "secret" not in str(row) and "hidden" not in str(row) and "wrong" not in str(row)
    assert row["duration_ms"] >= 0
