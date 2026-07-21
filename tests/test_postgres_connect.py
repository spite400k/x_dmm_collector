"""db.postgres_connect の IPv6 到達不可ハンドリングを検証する。"""

from unittest.mock import MagicMock, patch

import pytest

from db.postgres_connect import connect_from_env, connect_postgres


class TestConnectPostgresIpv6:
    def test_network_unreachable_raises_pooler_hint(self):
        err = OSError(
            'connection to server at "db.aaueetvhrbyqswejvmlc.supabase.co" '
            "(2406:da14:271:9901:defe:8b55:a52f:75d9), port 5432 failed: "
            "Network is unreachable"
        )
        with patch("db.postgres_connect.psycopg2.connect", side_effect=err):
            with pytest.raises(RuntimeError, match="Session pooler") as exc_info:
                connect_postgres(
                    host="db.aaueetvhrbyqswejvmlc.supabase.co",
                    dbname="postgres",
                    user="postgres",
                    password="x",
                    port=5432,
                    label="DB",
                )
        assert "IPv6" in str(exc_info.value)

    def test_url_path_uses_dsn(self):
        mock_conn = MagicMock()
        with patch("db.postgres_connect.psycopg2.connect", return_value=mock_conn) as connect:
            conn = connect_postgres(
                url="postgresql://postgres.ref:pw@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres",
                label="DB",
            )
        connect.assert_called_once()
        assert connect.call_args.args[0].startswith("postgresql://")
        assert connect.call_args.kwargs.get("sslmode") == "require"
        assert conn is mock_conn
        assert mock_conn.autocommit is False

    def test_connect_from_env_prefers_url(self, monkeypatch):
        monkeypatch.setenv(
            "DB_URL",
            "postgresql://postgres.ref:pw@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres",
        )
        monkeypatch.setenv("DB_HOST", "db.should-not-use.supabase.co")
        mock_conn = MagicMock()
        with patch("db.postgres_connect.psycopg2.connect", return_value=mock_conn) as connect:
            connect_from_env("DB")
        assert "pooler.supabase.com" in connect.call_args.args[0]

    def test_other_errors_are_reraised(self):
        with patch(
            "db.postgres_connect.psycopg2.connect",
            side_effect=RuntimeError("password authentication failed"),
        ):
            with pytest.raises(RuntimeError, match="password authentication failed"):
                connect_postgres(
                    host="aws-0-ap-northeast-1.pooler.supabase.com",
                    dbname="postgres",
                    user="postgres.ref",
                    password="bad",
                    label="DB",
                )
