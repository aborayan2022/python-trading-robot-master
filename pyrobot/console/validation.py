"""Input validation for the management console settings API.

A thin Pydantic layer that validates and sanitizes client-supplied theme and
branding updates before they reach the persisted SettingsManager dataclasses.
It rejects unknown keys, enforces hex color formats, and limits the logo URL
scheme to http(s)/relative to avoid data:/javascript: vectors.

The authoritative state remains the dataclasses in settings.py; this module
only validates the input boundary and maps validated values onto them.
"""

import re
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

COLOR_FIELDS = {
    "primary_color",
    "accent_color",
    "success_color",
    "warning_color",
    "danger_color",
    "bg_primary",
    "bg_secondary",
    "text_primary",
    "text_secondary",
}


def _validate_hex(value: str) -> str:
    if not HEX_COLOR_RE.match(value):
        raise ValueError(
            f"{value!r} is not a valid hex color; expected e.g. '#3b82f6'"
        )
    return value


class ThemeValidation(BaseModel):
    """Validated theme update; unknown keys are rejected via extra='forbid'.

    All fields are optional so callers can send partial updates; any field
    that IS provided must be a valid 6-digit hex color.
    """

    model_config = ConfigDict(extra="forbid")

    primary_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    success_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    warning_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    danger_color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    bg_primary: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    bg_secondary: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    text_primary: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    text_secondary: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class BrandingValidation(BaseModel):
    """Validated branding update; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    platform_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    platform_subtitle: Optional[str] = Field(default=None, max_length=120)
    logo_url: Optional[str] = Field(default=None, max_length=512)
    favicon_url: Optional[str] = Field(default=None, max_length=512)

    @field_validator("platform_name", "platform_subtitle")
    @classmethod
    def _strip_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return v.strip()

    @field_validator("logo_url", "favicon_url")
    @classmethod
    def _validate_image_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return v
        parsed = urlparse(v)
        # Allow http(s) absolute URLs and rooted relative paths. Reject
        # javascript:, data:, and other schemes.
        if parsed.scheme in ("http", "https"):
            return v
        if parsed.scheme == "" and v.startswith("/"):
            return v
        raise ValueError(
            "logo/favicon URL must be http(s) or a rooted relative path like /static/logo.png"
        )


class ThemeUpdateRequest(BaseModel):
    """Client-supplied theme/branding update, validated at the API boundary."""

    theme: Optional[ThemeValidation] = None
    branding: Optional[BrandingValidation] = None
