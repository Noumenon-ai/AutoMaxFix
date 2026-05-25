from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..models import FailureRecord
from . import cargo, generic, go, jest, mocha, pytest as pytest_scanner, vitest


Scanner = Callable[[str, Path], list[FailureRecord]]

SCANNERS: dict[str, Scanner] = {
    "pytest": pytest_scanner.scan,
    "jest": jest.scan,
    "vitest": vitest.scan,
    "mocha": mocha.scan,
    "go": go.scan,
    "cargo": cargo.scan,
    "generic": generic.scan,
}

__all__ = ["SCANNERS", "Scanner"]
