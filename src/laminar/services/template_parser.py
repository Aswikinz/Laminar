"""Direct parser for template-compliant Excel files."""

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from laminar.core.constants import SystemStep
from laminar.core.models import Process, Role, Step
from laminar.core.template import (
    ColumnType,
    TemplateValidationResult,
    validate_template,
)

logger = logging.getLogger(__name__)


class TemplateParseError(Exception):
    """Raised when template parsing fails."""


class TemplateParser:
    """Parses template-compliant Excel files directly without AI."""

    def __init__(self) -> None:
        """Initialize the template parser."""
        self._column_map: dict[ColumnType, str] = {}

    def validate_and_parse(
        self,
        xlsx_path: Path | str,
        sheet_name: str | None = None,
    ) -> tuple[TemplateValidationResult, Process | None]:
        """Validate an Excel file and parse if template-compliant.

        Args:
            xlsx_path: Path to the Excel file.
            sheet_name: Specific sheet to parse (None for first sheet).

        Returns:
            Tuple of (validation_result, process_or_none).
            Process is None if validation fails or can't parse directly.
        """
        xlsx_path = Path(xlsx_path)

        # Read the Excel file
        try:
            if sheet_name:
                df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
            else:
                df = pd.read_excel(xlsx_path, sheet_name=0)
        except Exception as e:
            logger.error("Failed to read Excel file: %s", e)
            return TemplateValidationResult(
                is_valid=False,
                confidence=0.0,
                matched_columns={},
                missing_required=[],
                unmatched_headers=[],
                messages=[f"Failed to read file: {e}"],
            ), None

        # Get headers
        headers = [str(col) for col in df.columns.tolist()]

        # Validate against template
        validation = validate_template(headers)

        if not validation.can_parse_directly:
            logger.info(
                "File not template-compliant (confidence: %.1f%%): %s",
                validation.confidence * 100,
                "; ".join(validation.messages),
            )
            return validation, None

        # Parse the file
        try:
            self._column_map = validation.matched_columns
            process = self._parse_dataframe(df, xlsx_path.stem)
            logger.info(
                "Successfully parsed template (confidence: %.1f%%)",
                validation.confidence * 100,
            )
            return validation, process
        except Exception as e:
            logger.error("Failed to parse template: %s", e)
            validation.messages.append(f"Parse error: {e}")
            return validation, None

    def _parse_dataframe(self, df: pd.DataFrame, process_name: str) -> Process:
        """Parse a DataFrame into a Process object.

        Args:
            df: The DataFrame to parse.
            process_name: Name for the process.

        Returns:
            Parsed Process object.
        """
        # Clean the dataframe
        df = df.fillna("")
        df = df.astype(str)
        df = df.map(lambda x: x.strip() if isinstance(x, str) else x)

        # Extract roles
        roles = self._extract_roles(df)

        # Extract steps
        steps = self._extract_steps(df, roles)

        # Add system start/end if not present
        steps = self._ensure_system_steps(steps)

        # Generate process ID
        process_id = re.sub(r"[^a-z0-9_]", "_", process_name.lower())

        return Process(
            process_id=process_id,
            process_name=process_name,
            process_roles=list(roles.values()),
            process_steps=steps,
        )

    def _get_cell(self, row: pd.Series, col_type: ColumnType) -> str:
        """Get a cell value by column type.

        Args:
            row: DataFrame row.
            col_type: The column type to get.

        Returns:
            Cell value as string, or empty string if not found.
        """
        if col_type not in self._column_map:
            return ""
        col_name = self._column_map[col_type]
        value = row.get(col_name, "")
        return str(value).strip() if value else ""

    def _extract_roles(self, df: pd.DataFrame) -> dict[str, Role]:
        """Extract unique roles from the data.

        Args:
            df: The DataFrame to extract from.

        Returns:
            Dictionary mapping role_id to Role objects.
        """
        roles: dict[str, Role] = {}

        if ColumnType.ROLE not in self._column_map:
            return roles

        role_col = self._column_map[ColumnType.ROLE]

        for role_title in df[role_col].unique():
            role_title = str(role_title).strip()
            if not role_title or role_title.lower() in ("", "nan", "none"):
                continue

            role_id = re.sub(r"[^a-z0-9_]", "_", role_title.lower())
            roles[role_id] = Role(role_id=role_id, role_title=role_title)

        return roles

    def _extract_steps(
        self,
        df: pd.DataFrame,
        roles: dict[str, Role],
    ) -> list[Step]:
        """Extract process steps from the data.

        Args:
            df: The DataFrame to extract from.
            roles: Dictionary of role_id to Role objects.

        Returns:
            List of Step objects.
        """
        steps: list[Step] = []
        step_id_map: dict[str, str] = {}  # Maps user step numbers to our step IDs

        # First pass: create step IDs
        for idx, row in df.iterrows():
            step_num = self._get_cell(row, ColumnType.STEP_NUMBER)
            step_title = self._get_cell(row, ColumnType.STEP_TITLE)

            if not step_title:
                continue

            # Generate step ID
            if step_num:
                step_id = f"step_{step_num}"
                step_id_map[step_num] = step_id
                step_id_map[str(step_num)] = step_id
            else:
                step_id = f"step_{idx}"

            # Also map by title (lowercase)
            step_id_map[step_title.lower()] = step_id

        # Second pass: create steps with resolved references
        for idx, row in df.iterrows():
            step_title = self._get_cell(row, ColumnType.STEP_TITLE)
            if not step_title:
                continue

            step_num = self._get_cell(row, ColumnType.STEP_NUMBER)
            step_id = step_id_map.get(step_num, f"step_{idx}") if step_num else f"step_{idx}"

            # Get role
            role_title = self._get_cell(row, ColumnType.ROLE)
            role_id = None
            if role_title:
                role_id = re.sub(r"[^a-z0-9_]", "_", role_title.lower())

            # Check if condition
            is_condition = self._is_condition(row)
            if is_condition:
                step_id = f"CONDITION::{step_id.replace('step_', '')}"

            # Get next steps
            next_step = self._resolve_step_ref(
                self._get_cell(row, ColumnType.NEXT_STEP),
                step_id_map,
            )
            yes_next = self._resolve_step_ref(
                self._get_cell(row, ColumnType.YES_NEXT),
                step_id_map,
            )
            no_next = self._resolve_step_ref(
                self._get_cell(row, ColumnType.NO_NEXT),
                step_id_map,
            )

            # Parse notes
            notes_str = self._get_cell(row, ColumnType.NOTES)
            notes = [n.strip() for n in notes_str.split(";") if n.strip()] if notes_str else []

            step = Step(
                step_id=step_id,
                step_role=role_id,
                step_title=step_title,
                step_description=self._get_cell(row, ColumnType.DESCRIPTION) or None,
                next_step=next_step if not is_condition else None,
                next_step_yes=yes_next if is_condition else None,
                next_step_no=no_next if is_condition else None,
                step_notes=notes,
                manual_system=self._get_cell(row, ColumnType.MANUAL_SYSTEM) or None,
                user_credentials=self._get_cell(row, ColumnType.USER_ID) or None,
                program_location=self._get_cell(row, ColumnType.PROGRAM_ID) or None,
                yes_when=self._get_cell(row, ColumnType.YES_WHEN) or None,
                no_when=self._get_cell(row, ColumnType.NO_WHEN) or None,
            )
            steps.append(step)

        return steps

    def _is_condition(self, row: pd.Series) -> bool:
        """Determine if a row represents a condition/decision.

        Args:
            row: DataFrame row.

        Returns:
            True if this is a condition step.
        """
        # Check explicit condition marker
        condition_val = self._get_cell(row, ColumnType.IS_CONDITION).lower()
        if condition_val in ("yes", "true", "1", "x", "condition", "decision"):
            return True

        # Check if has yes/no paths
        has_yes = bool(self._get_cell(row, ColumnType.YES_NEXT))
        has_no = bool(self._get_cell(row, ColumnType.NO_NEXT))
        if has_yes or has_no:
            return True

        # Check if title looks like a question
        title = self._get_cell(row, ColumnType.STEP_TITLE)
        if title.endswith("?"):
            return True

        return False

    def _resolve_step_ref(
        self,
        ref: str,
        step_id_map: dict[str, str],
    ) -> str | None:
        """Resolve a step reference to a step ID.

        Args:
            ref: The reference string (step number, title, or special value).
            step_id_map: Map of references to step IDs.

        Returns:
            Resolved step ID or None if empty.
        """
        if not ref:
            return None

        ref_lower = ref.lower().strip()

        # Check for special values
        if ref_lower in ("end", "finish", "done", "complete"):
            return SystemStep.END
        if ref_lower in ("abort", "cancel", "fail", "error", "reject"):
            return SystemStep.ABORT
        if ref_lower in ("start", "begin"):
            return SystemStep.START

        # Check direct map
        if ref in step_id_map:
            return step_id_map[ref]
        if ref_lower in step_id_map:
            return step_id_map[ref_lower]

        # Try as step number
        if ref.isdigit():
            return step_id_map.get(ref, f"step_{ref}")

        return None

    def _ensure_system_steps(self, steps: list[Step]) -> list[Step]:
        """Ensure START and END system steps exist.

        Args:
            steps: List of existing steps.

        Returns:
            Steps with START and END added if needed.
        """
        has_start = any(s.step_id == SystemStep.START for s in steps)
        has_end = any(s.step_id == SystemStep.END for s in steps)

        result = []

        # Add START if missing
        if not has_start and steps:
            first_step_id = steps[0].step_id
            result.append(Step(
                step_id=SystemStep.START,
                step_title="Start",
                next_step=first_step_id,
            ))

        result.extend(steps)

        # Add END if missing
        if not has_end:
            result.append(Step(
                step_id=SystemStep.END,
                step_title="End",
            ))

        # Check if ABORT is referenced but not defined
        abort_referenced = any(
            s.next_step == SystemStep.ABORT or
            s.next_step_yes == SystemStep.ABORT or
            s.next_step_no == SystemStep.ABORT
            for s in result
        )
        has_abort = any(s.step_id == SystemStep.ABORT for s in result)

        if abort_referenced and not has_abort:
            result.append(Step(
                step_id=SystemStep.ABORT,
                step_title="Abort",
            ))

        return result


def parse_template(
    xlsx_path: Path | str,
    sheet_name: str | None = None,
) -> tuple[TemplateValidationResult, Process | None]:
    """Convenience function to validate and parse an Excel template.

    Args:
        xlsx_path: Path to the Excel file.
        sheet_name: Specific sheet to parse (None for first sheet).

    Returns:
        Tuple of (validation_result, process_or_none).
    """
    parser = TemplateParser()
    return parser.validate_and_parse(xlsx_path, sheet_name)
