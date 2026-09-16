from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Branch:
    id: int | None
    branch_number: str
    internal_id: int
    description: str = ""


@dataclass(frozen=True, slots=True)
class Mango:
    id: int | None
    branch_id: int
    mango_number: int
    name: str
    vpn_ip: str
    lan_network: str
    mango_ip: str
    oven_ip: str
    certificate_created: bool = False
    config_created: bool = False
    branch_number: str = ""
    last_seen_at: str = ""


@dataclass(frozen=True, slots=True)
class MangoAddresses:
    name: str
    vpn_ip: str
    lan_network: str
    mango_ip: str
    oven_ip: str
