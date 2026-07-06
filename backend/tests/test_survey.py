"""Database connectivity smoke test."""

from backend.sim_env.mysql_simulator import MySQLSimulator


def test_connection():
    result = MySQLSimulator.execute_query(
        "SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema = DATABASE()"
    )
    assert result[0]["cnt"] >= 30

