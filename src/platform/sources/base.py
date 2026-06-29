"""Adapter contract. Adapters only emit RawRecord and land it — never touch canonical tables."""
from dataclasses import dataclass
from typing import Iterable, Protocol


@dataclass(frozen=True)
class RawRecord:
    route: str  # 'tournament' | 'usage' | 'replay'
    natural_key: str
    payload: dict
    url: str | None = None


class SourceAdapter(Protocol):
    source: str  # matches `source.name` row

    async def fetch(self, **kwargs) -> Iterable[RawRecord]:
        pass
