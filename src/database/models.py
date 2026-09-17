from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Network


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

    @property
    def oven_subnet_mask(self) -> str:
        return str(IPv4Network(self.lan_network).netmask)

    @property
    def oven_gateway(self) -> str:
        return self.mango_ip


@dataclass(frozen=True, slots=True)
class MangoAddresses:
    name: str
    vpn_ip: str
    lan_network: str
    mango_ip: str
    oven_ip: str
