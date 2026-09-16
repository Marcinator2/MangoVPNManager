import pytest

from openvpn.addressing import ValidationError, calculate_addresses


def test_calculates_name_and_addresses() -> None:
    values = calculate_addresses("0004", 4, 1)
    assert values.name == "0004_Mango1"
    assert values.vpn_ip == "10.8.4.1"
    assert values.lan_network == "10.4.1.0/24"
    assert values.mango_ip == "10.4.1.1"
    assert values.oven_ip == "10.4.1.101"


@pytest.mark.parametrize("branch_number", ["", "has space", "../escape", "a/b"])
def test_rejects_unsafe_branch_numbers(branch_number: str) -> None:
    with pytest.raises(ValidationError):
        calculate_addresses(branch_number, 4, 1)


@pytest.mark.parametrize("internal_id", [0, 8, 255])
def test_rejects_invalid_or_overlapping_internal_ids(internal_id: int) -> None:
    with pytest.raises(ValidationError):
        calculate_addresses("4", internal_id, 1)


@pytest.mark.parametrize("mango_number", [0, 11])
def test_rejects_mango_number_outside_operational_range(mango_number: int) -> None:
    with pytest.raises(ValidationError):
        calculate_addresses("4", 4, mango_number)


def test_allows_non_four_digit_branch_number() -> None:
    assert calculate_addresses("NORTH-12", 12, 10).name == "NORTH-12_Mango10"

