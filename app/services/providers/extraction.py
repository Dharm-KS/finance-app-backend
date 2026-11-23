"""Extraction of financial details from other forms / documents.

MVP: forms already send structured fields, so ``ManualExtractor`` passes them through. Later a
``GeminiExtractor`` implements :meth:`DocumentExtractor.extract` (free text or documents ->
structured fields) and is returned by :func:`get_extractor`; the API and the agents don't change.
"""

from abc import ABC, abstractmethod
from typing import Any


class DocumentExtractor(ABC):
    name: str

    @abstractmethod
    async def extract(self, category: str, data: dict[str, Any]) -> dict[str, Any]:
        """Return structured fields for ``category`` from the submitted form data."""


class ManualExtractor(DocumentExtractor):
    name = "manual"

    async def extract(self, category: str, data: dict[str, Any]) -> dict[str, Any]:
        return data


def get_extractor() -> DocumentExtractor:
    return ManualExtractor()
