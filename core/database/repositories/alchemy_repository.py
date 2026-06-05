"""Alchemy repository for elixir and material stock persistence."""

from typing import Dict
from core.database.repositories.base_repository import BaseRepository
from core.database.connection import get_connection


class AlchemyRepository(BaseRepository):
    """Repository for alchemy stock tables (elixirs, materials, draughts).

    Manages persistent stock counts for elixirs and base materials.
    Each item is identified by a stable string key (snake_case name).
    """

    def __init__(self) -> None:
        """Initialize with the elixir stock table as the primary table."""
        super().__init__("alchemy_elixir_stock")

    # ------------------------------------------------------------------
    # Elixir stock
    # ------------------------------------------------------------------

    def get_elixir_stock(self) -> Dict[str, int]:
        """Return all elixir stock as {elixir_key: quantity}."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT elixir_key, quantity FROM alchemy_elixir_stock")
            return {row["elixir_key"]: row["quantity"] for row in cursor.fetchall()}

    def set_elixir_quantity(self, elixir_key: str, quantity: int) -> None:
        """Upsert an elixir stock quantity."""
        if quantity < 0:
            quantity = 0
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO alchemy_elixir_stock (elixir_key, quantity)
                VALUES (?, ?)
                ON CONFLICT(elixir_key) DO UPDATE SET quantity = excluded.quantity
                """,
                (elixir_key, quantity),
            )

    def adjust_elixir_quantity(self, elixir_key: str, delta: int) -> int:
        """Add delta to an existing elixir stock, clamping to >= 0."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO alchemy_elixir_stock (elixir_key, quantity)
                VALUES (?, MAX(0, ?))
                ON CONFLICT(elixir_key) DO UPDATE
                SET quantity = MAX(0, quantity + excluded.quantity)
                """,
                (elixir_key, delta),
            )
            row = conn.execute(
                "SELECT quantity FROM alchemy_elixir_stock WHERE elixir_key = ?",
                (elixir_key,),
            ).fetchone()
            return row["quantity"] if row else 0

    # ------------------------------------------------------------------
    # Material stock
    # ------------------------------------------------------------------

    def get_material_stock(self) -> Dict[str, int]:
        """Return all material stock as {material_key: quantity}."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT material_key, quantity FROM alchemy_material_stock")
            return {row["material_key"]: row["quantity"] for row in cursor.fetchall()}

    def set_material_quantity(self, material_key: str, quantity: int) -> None:
        """Upsert a material stock quantity."""
        if quantity < 0:
            quantity = 0
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO alchemy_material_stock (material_key, quantity)
                VALUES (?, ?)
                ON CONFLICT(material_key) DO UPDATE SET quantity = excluded.quantity
                """,
                (material_key, quantity),
            )

    def adjust_material_quantity(self, material_key: str, delta: int) -> int:
        """Add delta to an existing material stock, clamping to >= 0."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO alchemy_material_stock (material_key, quantity)
                VALUES (?, MAX(0, ?))
                ON CONFLICT(material_key) DO UPDATE
                SET quantity = MAX(0, quantity + excluded.quantity)
                """,
                (material_key, delta),
            )
            row = conn.execute(
                "SELECT quantity FROM alchemy_material_stock WHERE material_key = ?",
                (material_key,),
            ).fetchone()
            return row["quantity"] if row else 0

    # ------------------------------------------------------------------
    # Draught stock
    # ------------------------------------------------------------------

    def get_draught_stock(self) -> Dict[str, int]:
        """Return all draught stock as {draught_key: quantity}."""
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT draught_key, quantity FROM alchemy_draught_stock")
            return {row["draught_key"]: row["quantity"] for row in cursor.fetchall()}

    def set_draught_quantity(self, draught_key: str, quantity: int) -> None:
        """Upsert a draught stock quantity."""
        if quantity < 0:
            quantity = 0
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO alchemy_draught_stock (draught_key, quantity)
                VALUES (?, ?)
                ON CONFLICT(draught_key) DO UPDATE SET quantity = excluded.quantity
                """,
                (draught_key, quantity),
            )
