from __future__ import annotations

from typing import Protocol

from app.models.types import OfferCandidate, ParsedIntent


class SourceAdapter(Protocol):
    name: str
    category: str

    def search(self, intent: ParsedIntent) -> list[OfferCandidate]:
        ...
