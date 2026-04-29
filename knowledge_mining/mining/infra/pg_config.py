"""PostgreSQL connection configuration for Mining v3.0."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class MiningDbConfig(BaseSettings):
    """PostgreSQL connection settings, loaded from environment variables."""

    pg_host: str = "121.89.90.178"
    pg_port: int = 5432
    pg_dbname: str = "kb_db"
    pg_user: str = "kb_user"
    pg_password: str = ""
    pg_sslmode: str = "disable"
    pg_gssencmode: str = "disable"
    pg_pool_min: int = 2
    pg_pool_max: int = 10

    model_config = {"env_prefix": "MINING_"}

    @property
    def conninfo(self) -> str:
        """Build psycopg connection string."""
        return (
            f"host={self.pg_host} "
            f"port={self.pg_port} "
            f"dbname={self.pg_dbname} "
            f"user={self.pg_user} "
            f"password={self.pg_password} "
            f"sslmode={self.pg_sslmode} "
            f"gssencmode={self.pg_gssencmode}"
        )
