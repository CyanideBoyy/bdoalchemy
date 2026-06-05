"""Base repository providing generic CRUD operations."""

from typing import List, Dict, Any, Optional
from core.database.connection import get_connection, get_db_path


class BaseRepository:
    """Generic repository for any database table.

    Child classes specify the table name; all CRUD operations work automatically.
    """

    _ALLOWED_TABLES: frozenset[str] = frozenset(
        {
            "alchemy_elixir_stock",
            "alchemy_material_stock",
            "alchemy_draught_stock",
        }
    )

    def __init__(self, table_name: str, db_path: str = None, id_column: str = "id"):
        if table_name not in self._ALLOWED_TABLES:
            raise ValueError(
                f"Unknown table {table_name!r}. "
                f"Allowed tables: {sorted(self._ALLOWED_TABLES)}"
            )
        self.table_name = table_name
        self.db_path = db_path or get_db_path()
        self.id_column = id_column

    def get_all(self) -> List[Dict[str, Any]]:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {self.table_name}")
            return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT * FROM {self.table_name} WHERE {self.id_column} = ?",
                (record_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update(self, record_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        set_clause = ", ".join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [record_id]
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE {self.table_name} SET {set_clause} WHERE {self.id_column} = ?",
                values,
            )
            return cursor.rowcount > 0

    def delete(self, record_id: int) -> bool:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM {self.table_name} WHERE {self.id_column} = ?",
                (record_id,),
            )
            return cursor.rowcount > 0

    def exists(self, record_id: int) -> bool:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT 1 FROM {self.table_name} WHERE {self.id_column} = ? LIMIT 1",
                (record_id,),
            )
            return cursor.fetchone() is not None

    def count(self) -> int:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            result = cursor.fetchone()
            return result[0] if result else 0
