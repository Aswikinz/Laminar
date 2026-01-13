"""Constants and enumerations for the Laminar application."""

from enum import StrEnum


class StepPrefix(StrEnum):
    """Prefixes used in step identifiers."""

    CONDITION = "CONDITION::"
    SYSTEM = "SYSTEM::"


class SystemStep(StrEnum):
    """System step identifiers."""

    START = "SYSTEM::START"
    END = "SYSTEM::END"
    ABORT = "SYSTEM::ABORT"


class MermaidShape(StrEnum):
    """Mermaid diagram shape identifiers."""

    CIRCLE = "circle"
    DOUBLE_CIRCLE = "double-circle"
    HEXAGON = "hexagon"
    BRACES = "braces"
    COMMENT = "comment"


class LinkStyle(StrEnum):
    """Link style definitions for Mermaid diagrams."""

    YES_PATH = "stroke:#0f0,stroke-width:2px;"
    NO_PATH = "stroke:#f00,stroke-width:2px;"
    NOTE_LINK = "stroke:#d3d3d3,stroke-width:2px;"


# File extensions for Excel files
EXCEL_EXTENSIONS = frozenset({".xlsx", ".xlsm", ".xls"})

# Default placeholder for missing values in Excel data
MISSING_VALUE_PLACEHOLDER = "--"
