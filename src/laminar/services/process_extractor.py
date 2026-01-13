"""Process extraction service with template parsing and AI fallback."""

import json
import logging
from pathlib import Path
from typing import Any

from laminar.config import Settings, get_settings
from laminar.core.models import Process
from laminar.core.template import TemplateValidationResult
from laminar.services.ai_analyzer import AIAnalyzer, AIAnalysisError
from laminar.services.excel_processor import ExcelProcessor
from laminar.services.mermaid_generator import generate_mermaid_from_process, save_mermaid_chart
from laminar.services.template_parser import TemplateParser

logger = logging.getLogger(__name__)


class ProcessExtractionError(Exception):
    """Raised when process extraction fails."""


class ProcessExtractor:
    """Extracts business processes from Excel files.

    Uses a two-stage approach:
    1. Try direct parsing if file matches expected template (fast, free)
    2. Fall back to AI analysis if template doesn't match (flexible, costs API)
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        force_ai: bool = False,
        force_template: bool = False,
    ) -> None:
        """Initialize the process extractor.

        Args:
            settings: Application settings.
            force_ai: Always use AI, skip template parsing.
            force_template: Only use template parsing, fail if not compliant.
        """
        self._settings = settings or get_settings()
        self._force_ai = force_ai
        self._force_template = force_template

        self._template_parser = TemplateParser()
        self._excel_processor = ExcelProcessor()
        self._ai_analyzer: AIAnalyzer | None = None

    @property
    def ai_analyzer(self) -> AIAnalyzer:
        """Lazy-load AI analyzer only when needed."""
        if self._ai_analyzer is None:
            self._ai_analyzer = AIAnalyzer(self._settings)
        return self._ai_analyzer

    def extract(
        self,
        xlsx_path: Path | str,
        sheet_name: str | None = None,
    ) -> tuple[Process, dict[str, Any]]:
        """Extract a business process from an Excel file.

        Args:
            xlsx_path: Path to the Excel file.
            sheet_name: Specific sheet to process (None for first).

        Returns:
            Tuple of (process, metadata).
            Metadata includes extraction method, confidence, etc.

        Raises:
            ProcessExtractionError: If extraction fails.
        """
        xlsx_path = Path(xlsx_path)

        if not xlsx_path.exists():
            raise ProcessExtractionError(f"File not found: {xlsx_path}")

        metadata: dict[str, Any] = {
            "file": xlsx_path.name,
            "sheet": sheet_name,
            "method": None,
            "confidence": 0.0,
            "template_validation": None,
        }

        # Stage 1: Try template parsing (unless forced to use AI)
        if not self._force_ai:
            logger.info("Attempting template-based parsing...")
            validation, process = self._template_parser.validate_and_parse(
                xlsx_path, sheet_name
            )
            metadata["template_validation"] = {
                "is_valid": validation.is_valid,
                "confidence": validation.confidence,
                "matched_columns": {k.value: v for k, v in validation.matched_columns.items()},
                "messages": validation.messages,
            }

            if process is not None:
                metadata["method"] = "template"
                metadata["confidence"] = validation.confidence
                logger.info(
                    "Successfully extracted process using template parser (%.0f%% confidence)",
                    validation.confidence * 100,
                )
                return process, metadata

            if self._force_template:
                raise ProcessExtractionError(
                    f"Template parsing failed and force_template=True. "
                    f"Messages: {'; '.join(validation.messages)}"
                )

            logger.info(
                "Template parsing not possible (%.0f%% confidence), falling back to AI",
                validation.confidence * 100,
            )

        # Stage 2: AI-based extraction
        logger.info("Using AI-based extraction...")
        try:
            process = self._extract_with_ai(xlsx_path, sheet_name)
            metadata["method"] = "ai"
            metadata["confidence"] = 0.9  # AI is generally reliable
            logger.info("Successfully extracted process using AI")
            return process, metadata
        except AIAnalysisError as e:
            raise ProcessExtractionError(f"AI extraction failed: {e}") from e

    def _extract_with_ai(
        self,
        xlsx_path: Path,
        sheet_name: str | None,
    ) -> Process:
        """Extract process using AI analysis.

        Args:
            xlsx_path: Path to the Excel file.
            sheet_name: Specific sheet to process.

        Returns:
            Extracted Process object.
        """
        # Extract CSV data
        csv_data = self._excel_processor.extract_sheets_as_csv(xlsx_path)

        if sheet_name and sheet_name in csv_data:
            sheet_csv = csv_data[sheet_name]
            target_sheet = sheet_name
        else:
            # Use first sheet
            target_sheet = next(iter(csv_data.keys()))
            sheet_csv = csv_data[target_sheet]

        # Analyze with AI (no image, just CSV)
        return self.ai_analyzer.analyze_sheet_to_process(
            csv_data=sheet_csv,
            sheet_name=target_sheet,
            image_path=None,  # No image - using CSV only
        )

    def extract_all_sheets(
        self,
        xlsx_path: Path | str,
    ) -> list[tuple[str, Process, dict[str, Any]]]:
        """Extract processes from all sheets in an Excel file.

        Args:
            xlsx_path: Path to the Excel file.

        Returns:
            List of (sheet_name, process, metadata) tuples.
        """
        xlsx_path = Path(xlsx_path)
        results: list[tuple[str, Process, dict[str, Any]]] = []

        sheet_names = self._excel_processor.get_sheet_names(xlsx_path)

        for sheet_name in sheet_names:
            try:
                process, metadata = self.extract(xlsx_path, sheet_name)
                results.append((sheet_name, process, metadata))
            except ProcessExtractionError as e:
                logger.error("Failed to extract sheet '%s': %s", sheet_name, e)

        return results


def extract_and_generate(
    xlsx_path: Path | str,
    output_dir: Path | str,
    sheet_name: str | None = None,
    *,
    force_ai: bool = False,
) -> dict[str, Any]:
    """Extract process from Excel and generate Mermaid diagram.

    Convenience function for the complete pipeline.

    Args:
        xlsx_path: Path to the Excel file.
        output_dir: Directory for output files.
        sheet_name: Specific sheet (None for all sheets).
        force_ai: Always use AI extraction.

    Returns:
        Dictionary with results and metadata.
    """
    xlsx_path = Path(xlsx_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extractor = ProcessExtractor(force_ai=force_ai)
    results: dict[str, Any] = {
        "file": xlsx_path.name,
        "sheets": [],
        "success": True,
        "errors": [],
    }

    if sheet_name:
        sheets_to_process = [sheet_name]
    else:
        sheets_to_process = extractor._excel_processor.get_sheet_names(xlsx_path)

    for sheet in sheets_to_process:
        sheet_result: dict[str, Any] = {"sheet": sheet}

        try:
            process, metadata = extractor.extract(xlsx_path, sheet)
            sheet_result["metadata"] = metadata

            # Save JSON
            json_path = output_dir / f"{sheet}_process.json"
            json_data = {
                "process_id": process.process_id,
                "process_name": process.process_name,
                "process_roles": [
                    {"role_id": r.role_id, "role_title": r.role_title, "role_notes": r.role_notes}
                    for r in process.process_roles
                ],
                "process_steps": [
                    {
                        "step_id": s.step_id,
                        "step_role": s.step_role,
                        "step_title": s.step_title,
                        "step_description": s.step_description,
                        "next_step": s.next_step,
                        "next_step_yes": s.next_step_yes,
                        "next_step_no": s.next_step_no,
                        "step_notes": s.step_notes,
                        "yes_when": s.yes_when,
                        "no_when": s.no_when,
                    }
                    for s in process.process_steps
                ],
            }
            json_path.write_text(json.dumps(json_data, indent=2))
            sheet_result["json_path"] = str(json_path)

            # Generate Mermaid
            mermaid = generate_mermaid_from_process(process)
            mermaid_path = output_dir / f"{sheet}_flowchart.mmd"
            save_mermaid_chart(mermaid, mermaid_path)
            sheet_result["mermaid_path"] = str(mermaid_path)

            sheet_result["success"] = True
            logger.info("Processed sheet '%s' -> %s", sheet, mermaid_path)

        except Exception as e:
            logger.error("Failed to process sheet '%s': %s", sheet, e)
            sheet_result["success"] = False
            sheet_result["error"] = str(e)
            results["success"] = False
            results["errors"].append(f"{sheet}: {e}")

        results["sheets"].append(sheet_result)

    return results
