# File Version: 0.1.0
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ServerSettings:
    host: str = "0.0.0.0"
    port: int = 8765
    template_path: Path = Path("templates")
    static_path: Path = Path("static")
    environment: str = "development"
    changelog_path: Path = Path("CHANGELOG.md")

    @classmethod
    def from_env(cls, base_path: Optional[Path] = None) -> "ServerSettings":
        root = base_path or Path.cwd()
        return cls(
            host=os.getenv("MFE_HOST", "0.0.0.0"),
            port=int(os.getenv("MFE_PORT", "8765")),
            template_path=root / os.getenv("MFE_TEMPLATE_PATH", "templates"),
            static_path=root / os.getenv("MFE_STATIC_PATH", "static"),
            environment=os.getenv("MFE_ENV", "development"),
            changelog_path=root / os.getenv("MFE_CHANGELOG", "CHANGELOG.md"),
        )
