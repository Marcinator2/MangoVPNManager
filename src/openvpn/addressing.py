from __future__ import annotations

import ipaddress
import re

from database.models import MangoAddresses


MIN_INTERNAL_ID = 1
MAX_INTERNAL_ID = 254
RESERVED_INTERNAL_IDS = {8}
MIN_MANGO_NUMBER = 1
MAX_MANGO_NUMBER = 10
_SAFE_BRANCH_NUMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$")


class ValidationError(ValueError):
    """A value cannot safely be used by the application."""


def validate_branch_number(branch_number: str) -> str:
    normalized = branch_number.strip()
    if not _SAFE_BRANCH_NUMBER.fullmatch(normalized):
        raise ValidationError(
            "Branch number must be 1-50 characters and contain only letters, "
            "digits, hyphens, or underscores."
        )
    return normalized


def validate_internal_id(internal_id: int) -> int:
    if not MIN_INTERNAL_ID <= internal_id <= MAX_INTERNAL_ID:
        raise ValidationError("Internal branch ID must be between 1 and 254.")
    if internal_id in RESERVED_INTERNAL_IDS:
        raise ValidationError(
            "Internal branch ID 8 is reserved because its LAN overlaps the "
            "10.8.0.0/16 VPN network."
        )
    return internal_id


def validate_mango_number(mango_number: int) -> int:
    if not MIN_MANGO_NUMBER <= mango_number <= MAX_MANGO_NUMBER:
        raise ValidationError("Mango number must be between 1 and 10.")
    return mango_number


def calculate_addresses(
    branch_number: str, internal_id: int, mango_number: int
) -> MangoAddresses:
    branch_number = validate_branch_number(branch_number)
    internal_id = validate_internal_id(internal_id)
    mango_number = validate_mango_number(mango_number)

    values = MangoAddresses(
        name=f"{branch_number}_Mango{mango_number}",
        vpn_ip=f"10.8.{internal_id}.{mango_number}",
        lan_network=f"10.{internal_id}.{mango_number}.0/24",
        mango_ip=f"10.{internal_id}.{mango_number}.1",
        oven_ip=f"10.{internal_id}.{mango_number}.{100 + mango_number}",
    )
    # Keep the formulas guarded even if their allowed ranges change later.
    ipaddress.ip_address(values.vpn_ip)
    ipaddress.ip_network(values.lan_network)
    ipaddress.ip_address(values.mango_ip)
    ipaddress.ip_address(values.oven_ip)
    return values

