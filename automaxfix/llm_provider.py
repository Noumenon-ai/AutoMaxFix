from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from .models import PatchProposal, RepoContext, Ticket


class ProviderError(RuntimeError):
    """Raised when a provider cannot produce a response."""


class LLMProvider(ABC):
    @abstractmethod
    def generate_patch(self, ticket: Ticket, repo_context: RepoContext) -> PatchProposal:
        raise NotImplementedError

    @abstractmethod
    def generate_reproduction_test(
        self, ticket: Ticket, repo_context: RepoContext
    ) -> str | None:
        raise NotImplementedError


class MockProvider(LLMProvider):
    def __init__(
        self,
        *,
        patch_proposal: PatchProposal | None = None,
        reproduction_text: str | None = None,
    ) -> None:
        self._patch_proposal = patch_proposal or PatchProposal(
            summary="Mock patch proposal", files=[]
        )
        self._reproduction_text = reproduction_text

    def generate_patch(self, ticket: Ticket, repo_context: RepoContext) -> PatchProposal:
        del ticket, repo_context
        return self._patch_proposal

    def generate_reproduction_test(
        self, ticket: Ticket, repo_context: RepoContext
    ) -> str | None:
        del ticket, repo_context
        return self._reproduction_text


class FileProvider(LLMProvider):
    def __init__(
        self,
        *,
        patch_file: Path,
        reproduction_file: Path | None = None,
    ) -> None:
        self.patch_file = patch_file
        self.reproduction_file = reproduction_file

    def generate_patch(self, ticket: Ticket, repo_context: RepoContext) -> PatchProposal:
        del ticket, repo_context
        if not self.patch_file.exists():
            raise ProviderError(f"Patch file not found: {self.patch_file}")
        payload = json.loads(self.patch_file.read_text(encoding="utf-8"))
        return PatchProposal.from_dict(payload)

    def generate_reproduction_test(
        self, ticket: Ticket, repo_context: RepoContext
    ) -> str | None:
        del ticket, repo_context
        if self.reproduction_file is None:
            return None
        if not self.reproduction_file.exists():
            raise ProviderError(f"Reproduction file not found: {self.reproduction_file}")
        return self.reproduction_file.read_text(encoding="utf-8")


def load_provider_from_environment(base_dir: Path) -> LLMProvider | None:
    provider_kind = os.environ.get("AUTOMAXFIX_PROVIDER", "").strip().lower()
    if not provider_kind:
        return None
    if provider_kind == "file":
        patch_raw = os.environ.get("AUTOMAXFIX_PATCH_FILE", "").strip()
        if not patch_raw:
            raise ProviderError("AUTOMAXFIX_PATCH_FILE is required for FileProvider")
        repro_raw = os.environ.get("AUTOMAXFIX_REPRO_FILE", "").strip()
        patch_file = Path(patch_raw)
        if not patch_file.is_absolute():
            patch_file = (base_dir / patch_file).resolve()
        reproduction_file = None
        if repro_raw:
            reproduction_file = Path(repro_raw)
            if not reproduction_file.is_absolute():
                reproduction_file = (base_dir / reproduction_file).resolve()
        return FileProvider(patch_file=patch_file, reproduction_file=reproduction_file)
    if provider_kind == "mock":
        patch_json = os.environ.get("AUTOMAXFIX_MOCK_PATCH_JSON", "").strip()
        repro_text = os.environ.get("AUTOMAXFIX_MOCK_REPRO_TEXT", "")
        proposal = PatchProposal(summary="Mock patch proposal", files=[])
        if patch_json:
            proposal = PatchProposal.from_dict(json.loads(patch_json))
        return MockProvider(patch_proposal=proposal, reproduction_text=repro_text or None)
    raise ProviderError(f"Unsupported provider kind: {provider_kind}")
