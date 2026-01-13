"""Excel template schema definition and validation."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ColumnType(StrEnum):
    """Types of columns in the template."""

    STEP_NUMBER = "step_number"
    ROLE = "role"
    STEP_TITLE = "step_title"
    DESCRIPTION = "description"
    NEXT_STEP = "next_step"
    IS_CONDITION = "is_condition"
    YES_NEXT = "yes_next"
    NO_NEXT = "no_next"
    YES_WHEN = "yes_when"
    NO_WHEN = "no_when"
    NOTES = "notes"
    MANUAL_SYSTEM = "manual_system"
    SYSTEM_NAME = "system_name"
    USER_ID = "user_id"
    PROGRAM_ID = "program_id"


@dataclass
class ColumnMapping:
    """Maps a template column to its properties."""

    column_type: ColumnType
    required: bool = False
    aliases: list[str] = field(default_factory=list)

    def matches(self, header: str) -> bool:
        """Check if a header matches this column.

        Args:
            header: The header text to check.

        Returns:
            True if the header matches this column type.
        """
        header_lower = header.lower().strip()
        # Check exact match with column type
        if header_lower == self.column_type.value.replace("_", " "):
            return True
        if header_lower == self.column_type.value.replace("_", ""):
            return True
        if header_lower == self.column_type.value:
            return True
        # Check aliases
        return any(alias.lower() == header_lower for alias in self.aliases)


# Standard template column definitions
TEMPLATE_COLUMNS: list[ColumnMapping] = [
    ColumnMapping(
        column_type=ColumnType.STEP_NUMBER,
        required=True,
        aliases=["step #", "step", "step no", "step no.", "#", "no", "no.", "id", "step_id"],
    ),
    ColumnMapping(
        column_type=ColumnType.ROLE,
        required=True,
        aliases=["role", "actor", "responsible", "owner", "assigned to", "performer", "swimlane"],
    ),
    ColumnMapping(
        column_type=ColumnType.STEP_TITLE,
        required=True,
        aliases=["title", "step title", "name", "step name", "action", "activity", "task"],
    ),
    ColumnMapping(
        column_type=ColumnType.DESCRIPTION,
        required=False,
        aliases=["description", "desc", "details", "step description", "explanation"],
    ),
    ColumnMapping(
        column_type=ColumnType.NEXT_STEP,
        required=False,
        aliases=["next", "next step", "goes to", "then", "flow to", "->"],
    ),
    ColumnMapping(
        column_type=ColumnType.IS_CONDITION,
        required=False,
        aliases=["condition", "is condition", "decision", "condition?", "is decision", "type"],
    ),
    ColumnMapping(
        column_type=ColumnType.YES_NEXT,
        required=False,
        aliases=["yes", "yes next", "yes ->", "yes→", "if yes", "true", "yes path", "on yes"],
    ),
    ColumnMapping(
        column_type=ColumnType.NO_NEXT,
        required=False,
        aliases=["no", "no next", "no ->", "no→", "if no", "false", "no path", "on no"],
    ),
    ColumnMapping(
        column_type=ColumnType.YES_WHEN,
        required=False,
        aliases=["yes when", "yes condition", "yes if", "condition for yes"],
    ),
    ColumnMapping(
        column_type=ColumnType.NO_WHEN,
        required=False,
        aliases=["no when", "no condition", "no if", "condition for no"],
    ),
    ColumnMapping(
        column_type=ColumnType.NOTES,
        required=False,
        aliases=["notes", "note", "comments", "remarks", "annotations"],
    ),
    ColumnMapping(
        column_type=ColumnType.MANUAL_SYSTEM,
        required=False,
        aliases=["manual/system", "manual or system", "type", "execution type", "mode"],
    ),
    ColumnMapping(
        column_type=ColumnType.SYSTEM_NAME,
        required=False,
        aliases=["system", "system name", "application", "app", "tool"],
    ),
    ColumnMapping(
        column_type=ColumnType.USER_ID,
        required=False,
        aliases=["user", "user id", "login", "username", "user name"],
    ),
    ColumnMapping(
        column_type=ColumnType.PROGRAM_ID,
        required=False,
        aliases=["program", "program id", "t-code", "tcode", "screen", "transaction"],
    ),
]


@dataclass
class TemplateValidationResult:
    """Result of template validation."""

    is_valid: bool
    confidence: float  # 0.0 to 1.0
    matched_columns: dict[ColumnType, str]  # column_type -> actual header name
    missing_required: list[ColumnType]
    unmatched_headers: list[str]
    messages: list[str] = field(default_factory=list)

    @property
    def can_parse_directly(self) -> bool:
        """Check if the file can be parsed without AI.

        Returns True if confidence is high enough and all required columns present.
        """
        return self.is_valid and self.confidence >= 0.7 and not self.missing_required


def validate_template(headers: list[str]) -> TemplateValidationResult:
    """Validate Excel headers against the template schema.

    Args:
        headers: List of column headers from the Excel file.

    Returns:
        TemplateValidationResult with validation details.
    """
    matched_columns: dict[ColumnType, str] = {}
    unmatched_headers: list[str] = []
    messages: list[str] = []

    # Clean headers
    clean_headers = [h.strip() if isinstance(h, str) else str(h) for h in headers]

    # Try to match each header to a column type
    for header in clean_headers:
        if not header or header.startswith("Unnamed"):
            continue

        matched = False
        for col_mapping in TEMPLATE_COLUMNS:
            if col_mapping.matches(header):
                if col_mapping.column_type not in matched_columns:
                    matched_columns[col_mapping.column_type] = header
                    matched = True
                    break

        if not matched:
            unmatched_headers.append(header)

    # Check for missing required columns
    missing_required: list[ColumnType] = []
    for col_mapping in TEMPLATE_COLUMNS:
        if col_mapping.required and col_mapping.column_type not in matched_columns:
            missing_required.append(col_mapping.column_type)

    # Calculate confidence score
    total_columns = len(TEMPLATE_COLUMNS)
    matched_count = len(matched_columns)
    required_matched = sum(
        1 for col in TEMPLATE_COLUMNS
        if col.required and col.column_type in matched_columns
    )
    required_total = sum(1 for col in TEMPLATE_COLUMNS if col.required)

    # Confidence based on: required columns (60%) + optional columns (40%)
    if required_total > 0:
        required_score = required_matched / required_total
    else:
        required_score = 1.0

    optional_score = matched_count / total_columns if total_columns > 0 else 0
    confidence = (required_score * 0.6) + (optional_score * 0.4)

    # Determine validity
    is_valid = len(missing_required) == 0 and matched_count >= 3

    # Build messages
    if missing_required:
        messages.append(f"Missing required columns: {', '.join(c.value for c in missing_required)}")
    if unmatched_headers:
        messages.append(f"Unrecognized columns (will be ignored): {', '.join(unmatched_headers)}")
    if matched_columns:
        messages.append(f"Matched {len(matched_columns)} template columns")

    return TemplateValidationResult(
        is_valid=is_valid,
        confidence=confidence,
        matched_columns=matched_columns,
        missing_required=missing_required,
        unmatched_headers=unmatched_headers,
        messages=messages,
    )


# Example template structure for documentation
TEMPLATE_EXAMPLE = """
Expected Excel Template Structure:
==================================

| Step # | Role     | Step Title        | Description          | Next Step | Condition? | Yes→ | No→ | Notes    |
|--------|----------|-------------------|----------------------|-----------|------------|------|-----|----------|
| 1      | Officer  | Receive report    | Get customer list    | 2         |            |      |     |          |
| 2      | Officer  | Review data       | Check completeness   | 3         |            |      |     |          |
| 3      |          | Data complete?    | Verify all fields    |           | Yes        | 4    | 2   | Decision |
| 4      | Manager  | Approve           | Final approval       | 5         |            |      |     |          |
| 5      |          | Approved?         |                      |           | Yes        | END  | 6   |          |
| 6      | Officer  | Revise            | Make corrections     | 3         |            |      |     |          |

Required Columns:
- Step # (or: step, id, no)
- Role (or: actor, responsible, owner)
- Step Title (or: title, name, action, activity)

Optional Columns:
- Description
- Next Step (for sequential flow)
- Condition? (mark Yes/True for decision points)
- Yes→ / No→ (next steps for conditions)
- Yes When / No When (explanations for conditions)
- Notes
- Manual/System, System Name, User ID, Program ID

Special Values:
- START: First step (auto-detected if not specified)
- END: Process completion
- ABORT: Process termination due to error/rejection

Tips:
- Leave Role empty for decision/condition steps
- Use step numbers or step titles in Next Step, Yes→, No→ columns
- Conditions are auto-detected if Yes→ or No→ columns have values
"""
