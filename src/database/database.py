from __future__ import annotations

import sqlite3
from pathlib import Path

from database.models import Branch, Mango
from openvpn.addressing import (
    MAX_INTERNAL_ID,
    MIN_INTERNAL_ID,
    RESERVED_INTERNAL_IDS,
    MAX_MANGO_NUMBER,
    ValidationError,
    calculate_addresses,
    validate_branch_number,
    validate_internal_id,
)


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS branches (
                id INTEGER PRIMARY KEY,
                branch_number TEXT NOT NULL COLLATE NOCASE UNIQUE,
                internal_id INTEGER NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS mangos (
                id INTEGER PRIMARY KEY,
                branch_id INTEGER NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
                mango_number INTEGER NOT NULL,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                vpn_ip TEXT NOT NULL UNIQUE,
                lan_network TEXT NOT NULL UNIQUE,
                mango_ip TEXT NOT NULL UNIQUE,
                oven_ip TEXT NOT NULL UNIQUE,
                certificate_created INTEGER NOT NULL DEFAULT 0 CHECK (certificate_created IN (0, 1)),
                config_created INTEGER NOT NULL DEFAULT 0 CHECK (config_created IN (0, 1)),
                UNIQUE (branch_id, mango_number)
            );
            """
        )
        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(mangos)").fetchall()
        }
        if "last_seen_at" not in columns:
            self.connection.execute(
                "ALTER TABLE mangos ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT ''"
            )
        self.connection.commit()

    def list_branches(self) -> list[Branch]:
        rows = self.connection.execute(
            "SELECT id, branch_number, internal_id, description FROM branches "
            "ORDER BY branch_number COLLATE NOCASE"
        ).fetchall()
        return [Branch(**dict(row)) for row in rows]

    def next_available_internal_id(self) -> int:
        used = {
            row["internal_id"]
            for row in self.connection.execute("SELECT internal_id FROM branches").fetchall()
        }
        for internal_id in range(MIN_INTERNAL_ID, MAX_INTERNAL_ID + 1):
            if internal_id not in used and internal_id not in RESERVED_INTERNAL_IDS:
                return internal_id
        raise ValidationError('No free internal location ID is available.', translation_key='validation_no_free_id')

    def add_branch(
        self,
        branch_number: str,
        internal_id: int | None = None,
        description: str = "",
    ) -> Branch:
        return self.add_branch_with_mangos(
            branch_number,
            mango_count=0,
            description=description,
            internal_id=internal_id,
        )

    def add_branch_with_mangos(
        self,
        branch_number: str,
        mango_count: int,
        description: str = "",
        internal_id: int | None = None,
    ) -> Branch:
        if not 0 <= mango_count <= MAX_MANGO_NUMBER:
            raise ValidationError('Number of Routers must be between 0 and 10.', translation_key='validation_router_count')
        branch_number = validate_branch_number(branch_number)
        if internal_id is None:
            internal_id = self.next_available_internal_id()
        internal_id = validate_internal_id(internal_id)
        description = description.strip()
        try:
            with self.connection:
                cursor = self.connection.execute(
                    "INSERT INTO branches(branch_number, internal_id, description) VALUES (?, ?, ?)",
                    (branch_number, internal_id, description),
                )
                branch_id = cursor.lastrowid
                for mango_number in range(1, mango_count + 1):
                    values = calculate_addresses(branch_number, internal_id, mango_number)
                    self.connection.execute(
                        """INSERT INTO mangos(
                               branch_id, mango_number, name, vpn_ip, lan_network,
                               mango_ip, oven_ip
                           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            branch_id,
                            mango_number,
                            values.name,
                            values.vpn_ip,
                            values.lan_network,
                            values.mango_ip,
                            values.oven_ip,
                        ),
                    )
        except sqlite3.IntegrityError as exc:
            raise ValidationError('Location, Router names, and addresses must be unique.', translation_key='validation_unique') from exc
        return Branch(branch_id, branch_number, internal_id, description)

    def update_branch(self, branch: Branch) -> None:
        if branch.id is None:
            raise ValidationError('Cannot update a location without an ID.', translation_key='validation_location_id')
        branch_number = validate_branch_number(branch.branch_number)
        internal_id = validate_internal_id(branch.internal_id)
        mangos = self.connection.execute(
            "SELECT id, mango_number FROM mangos WHERE branch_id = ?", (branch.id,)
        ).fetchall()
        try:
            with self.connection:
                self.connection.execute(
                    "UPDATE branches SET branch_number = ?, internal_id = ?, description = ? WHERE id = ?",
                    (branch_number, internal_id, branch.description.strip(), branch.id),
                )
                if self.connection.execute("SELECT changes()").fetchone()[0] == 0:
                    raise ValidationError('Location no longer exists.', translation_key='validation_location_missing')
                for mango in mangos:
                    values = calculate_addresses(branch_number, internal_id, mango["mango_number"])
                    self.connection.execute(
                        """UPDATE mangos SET name = ?, vpn_ip = ?, lan_network = ?,
                           mango_ip = ?, oven_ip = ? WHERE id = ?""",
                        (
                            values.name,
                            values.vpn_ip,
                            values.lan_network,
                            values.mango_ip,
                            values.oven_ip,
                            mango["id"],
                        ),
                    )
        except sqlite3.IntegrityError as exc:
            raise ValidationError('The changed location would create duplicate names or addresses.', translation_key='validation_location_duplicate') from exc

    def delete_branch(self, branch_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM branches WHERE id = ?", (branch_id,))

    def list_mangos(self, branch_id: int | None = None) -> list[Mango]:
        sql = """
            SELECT m.id, m.branch_id, m.mango_number, m.name, m.vpn_ip,
                   m.lan_network, m.mango_ip, m.oven_ip,
                   m.certificate_created, m.config_created, b.branch_number,
                   m.last_seen_at
            FROM mangos m JOIN branches b ON b.id = m.branch_id
        """
        parameters: tuple[int, ...] = ()
        if branch_id is not None:
            sql += " WHERE m.branch_id = ?"
            parameters = (branch_id,)
        sql += " ORDER BY b.branch_number COLLATE NOCASE, m.mango_number"
        rows = self.connection.execute(sql, parameters).fetchall()
        return [self._mango_from_row(row) for row in rows]

    def add_mango(self, branch_id: int, mango_number: int) -> Mango:
        branch = self.connection.execute(
            "SELECT branch_number, internal_id FROM branches WHERE id = ?", (branch_id,)
        ).fetchone()
        if branch is None:
            raise ValidationError('Selected location no longer exists.', translation_key='validation_location_missing')
        values = calculate_addresses(branch["branch_number"], branch["internal_id"], mango_number)
        try:
            cursor = self.connection.execute(
                """INSERT INTO mangos(
                       branch_id, mango_number, name, vpn_ip, lan_network, mango_ip, oven_ip
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    branch_id,
                    mango_number,
                    values.name,
                    values.vpn_ip,
                    values.lan_network,
                    values.mango_ip,
                    values.oven_ip,
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValidationError('This Router or one of its calculated addresses already exists.', translation_key='validation_router_duplicate') from exc
        return Mango(
            cursor.lastrowid,
            branch_id,
            mango_number,
            values.name,
            values.vpn_ip,
            values.lan_network,
            values.mango_ip,
            values.oven_ip,
        )

    def update_mango(self, mango_id: int, branch_id: int, mango_number: int) -> None:
        branch = self.connection.execute(
            "SELECT branch_number, internal_id FROM branches WHERE id = ?", (branch_id,)
        ).fetchone()
        if branch is None:
            raise ValidationError('Selected location no longer exists.', translation_key='validation_location_missing')
        values = calculate_addresses(branch["branch_number"], branch["internal_id"], mango_number)
        try:
            with self.connection:
                self.connection.execute(
                    """UPDATE mangos SET branch_id = ?, mango_number = ?, name = ?,
                       vpn_ip = ?, lan_network = ?, mango_ip = ?, oven_ip = ?,
                       config_created = 0 WHERE id = ?""",
                    (
                        branch_id,
                        mango_number,
                        values.name,
                        values.vpn_ip,
                        values.lan_network,
                        values.mango_ip,
                        values.oven_ip,
                        mango_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValidationError('This Router or one of its calculated addresses already exists.', translation_key='validation_router_duplicate') from exc

    def delete_mango(self, mango_id: int) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM mangos WHERE id = ?", (mango_id,))

    def set_certificate_created(self, mango_id: int, created: bool) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE mangos SET certificate_created = ? WHERE id = ?",
                (int(created), mango_id),
            )

    def mark_configs_created(self, mango_ids: list[int]) -> None:
        with self.connection:
            self.connection.executemany(
                "UPDATE mangos SET config_created = 1 WHERE id = ?",
                [(mango_id,) for mango_id in mango_ids],
            )

    def reset_config_statuses(
        self,
        mango_ids: list[int] | None = None,
    ) -> None:
        with self.connection:
            if mango_ids is None:
                self.connection.execute(
                    "UPDATE mangos SET config_created = 0"
                )
            else:
                self.connection.executemany(
                    "UPDATE mangos SET config_created = 0 WHERE id = ?",
                    [(mango_id,) for mango_id in mango_ids],
                )

    def mark_mangos_seen(self, mango_ids: list[int], seen_at: str) -> None:
        if not mango_ids:
            return
        with self.connection:
            self.connection.executemany(
                "UPDATE mangos SET last_seen_at = ? WHERE id = ?",
                [(seen_at, mango_id) for mango_id in mango_ids],
            )

    @staticmethod
    def _mango_from_row(row: sqlite3.Row) -> Mango:
        values = dict(row)
        values["certificate_created"] = bool(values["certificate_created"])
        values["config_created"] = bool(values["config_created"])
        return Mango(**values)
