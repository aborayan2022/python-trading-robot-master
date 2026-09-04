"""Console Settings — Theme and Branding Configuration.

Persisted to data/console_settings.json. Manager-only via API.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from pyrobot.logging_config import get_logger

logger = get_logger("console_settings")

DEFAULT_SETTINGS_PATH = Path("data/console_settings.json")


@dataclass
class ThemeSettings:
    """Visual theme configuration for the management console."""

    primary_color: str = "#3b82f6"
    accent_color: str = "#06b6d4"
    success_color: str = "#10b981"
    warning_color: str = "#f59e0b"
    danger_color: str = "#ef4444"
    bg_primary: str = "#0a0e17"
    bg_secondary: str = "#111827"
    text_primary: str = "#f8fafc"
    text_secondary: str = "#94a3b8"


@dataclass
class BrandingSettings:
    """Branding configuration for the management console."""

    platform_name: str = "PyRobot"
    platform_subtitle: str = "Management Console"
    logo_url: str = ""
    favicon_url: str = ""


@dataclass
class ConsoleSettings:
    """Full console settings bundle."""

    theme: ThemeSettings = field(default_factory=ThemeSettings)
    branding: BrandingSettings = field(default_factory=BrandingSettings)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme": asdict(self.theme),
            "branding": asdict(self.branding),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsoleSettings":
        theme_data = data.get("theme", {})
        branding_data = data.get("branding", {})
        return cls(
            theme=ThemeSettings(**{k: v for k, v in theme_data.items() if k in ThemeSettings.__dataclass_fields__}),
            branding=BrandingSettings(**{k: v for k, v in branding_data.items() if k in BrandingSettings.__dataclass_fields__}),
        )


class SettingsManager:
    """Thread-safe persistent settings manager."""

    def __init__(self, settings_path: Optional[Path | str] = None) -> None:
        self.settings_path = Path(settings_path) if settings_path else DEFAULT_SETTINGS_PATH
        self._settings: ConsoleSettings = ConsoleSettings()
        self._load()

    def _load(self) -> None:
        if self.settings_path.exists():
            try:
                data = json.loads(self.settings_path.read_text(encoding="utf-8"))
                self._settings = ConsoleSettings.from_dict(data)
                logger.info("Loaded console settings from %s", self.settings_path)
            except Exception as exc:
                logger.warning("Failed to load settings from %s: %s — using defaults", self.settings_path, exc)
                self._settings = ConsoleSettings()
        else:
            self._settings = ConsoleSettings()
            self._save()

    def _save(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(self._settings.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self) -> ConsoleSettings:
        return self._settings

    def update(self, data: Dict[str, Any]) -> ConsoleSettings:
        """Update settings from a partial dict (merges, does not replace)."""
        current = self._settings.to_dict()
        if "theme" in data and isinstance(data["theme"], dict):
            current["theme"].update(data["theme"])
        if "branding" in data and isinstance(data["branding"], dict):
            current["branding"].update(data["branding"])
        self._settings = ConsoleSettings.from_dict(current)
        self._save()
        logger.info("Console settings updated and saved")
        return self._settings

    def reset(self) -> ConsoleSettings:
        """Reset to defaults."""
        self._settings = ConsoleSettings()
        self._save()
        logger.info("Console settings reset to defaults")
        return self._settings
