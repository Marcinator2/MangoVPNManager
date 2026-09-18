from pathlib import Path

import pytest

from database.database import Database
from database.models import Branch
from openvpn.addressing import ValidationError


@pytest.fixture
def database(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


def test_branch_and_mango_round_trip(database: Database) -> None:
    branch = database.add_branch("0004", 4, "Test branch")
    mango = database.add_mango(branch.id or 0, 2)
    assert mango.name == "0004_Mango2"
    stored = database.list_mangos(branch.id)
    assert len(stored) == 1
    assert stored[0].oven_ip == "10.4.2.102"


def test_internal_id_is_assigned_automatically(database: Database) -> None:
    first = database.add_branch("FIRST")
    second = database.add_branch("SECOND")
    assert first.internal_id == 1
    assert second.internal_id == 2


def test_duplicate_descriptions_are_allowed_on_create_and_update(database: Database) -> None:
    first = database.add_branch_with_mangos("0001", 1, "Same description")
    second = database.add_branch_with_mangos("0002", 1, "Same description")
    database.update_branch(Branch(second.id, "0002", second.internal_id, "Changed"))
    database.update_branch(Branch(second.id, "0002", second.internal_id, first.description))
    assert [branch.description for branch in database.list_branches()] == [
        "Same description", "Same description",
    ]
    assert len({mango.vpn_ip for mango in database.list_mangos()}) == 2


def test_automatic_internal_id_skips_used_and_reserved_values(database: Database) -> None:
    for internal_id in range(1, 8):
        database.add_branch(f"BRANCH-{internal_id}", internal_id)
    automatic = database.add_branch("AFTER-RESERVED")
    assert automatic.internal_id == 9


def test_branch_can_create_sequential_mangos_atomically(database: Database) -> None:
    branch = database.add_branch_with_mangos("BULK", 4, description="Four routers")
    mangos = database.list_mangos(branch.id)
    assert [mango.mango_number for mango in mangos] == [1, 2, 3, 4]
    assert [mango.name for mango in mangos] == [
        "BULK_Mango1",
        "BULK_Mango2",
        "BULK_Mango3",
        "BULK_Mango4",
    ]


@pytest.mark.parametrize("mango_count", [-1, 11])
def test_branch_rejects_invalid_initial_mango_count(
    database: Database, mango_count: int
) -> None:
    with pytest.raises(ValidationError):
        database.add_branch_with_mangos("INVALID", mango_count)
    assert database.list_branches() == []


def test_duplicate_branch_fields_are_rejected(database: Database) -> None:
    database.add_branch("0004", 4)
    with pytest.raises(ValidationError):
        database.add_branch("0004", 5)
    with pytest.raises(ValidationError):
        database.add_branch("0005", 4)


def test_duplicate_mango_is_rejected(database: Database) -> None:
    branch = database.add_branch("0004", 4)
    database.add_mango(branch.id or 0, 1)
    with pytest.raises(ValidationError):
        database.add_mango(branch.id or 0, 1)


def test_updating_branch_recalculates_mango(database: Database) -> None:
    branch = database.add_branch("4", 4)
    database.add_mango(branch.id or 0, 1)
    database.update_branch(Branch(branch.id, "WEST", 5, "Changed"))
    mango = database.list_mangos(branch.id)[0]
    assert mango.name == "WEST_Mango1"
    assert mango.vpn_ip == "10.8.5.1"


def test_deleting_branch_cascades_to_mangos(database: Database) -> None:
    branch = database.add_branch("4", 4)
    database.add_mango(branch.id or 0, 1)
    database.delete_branch(branch.id or 0)
    assert database.list_mangos() == []




def test_config_status_can_be_invalidated(database: Database) -> None:
    branch = database.add_branch_with_mangos("STATUS", 2)
    mangos = database.list_mangos(branch.id)
    ids = [mango.id or 0 for mango in mangos]
    database.mark_configs_created(ids)
    assert all(mango.config_created for mango in database.list_mangos(branch.id))

    database.reset_config_statuses([ids[0]])
    states = [mango.config_created for mango in database.list_mangos(branch.id)]
    assert states == [False, True]

    database.reset_config_statuses()
    assert not any(
        mango.config_created for mango in database.list_mangos(branch.id)
    )


def test_last_seen_is_persisted(database: Database) -> None:
    branch = database.add_branch_with_mangos("SEEN", 1)
    mango = database.list_mangos(branch.id)[0]
    database.mark_mangos_seen([mango.id or 0], "2026-09-16T10:00:05+02:00")
    assert database.list_mangos(branch.id)[0].last_seen_at == "2026-09-16T10:00:05+02:00"
