"""AI-powered business process analysis service using Claude."""

import json
import logging
from pathlib import Path
from typing import Any

import anthropic

from laminar.config import Settings, get_settings
from laminar.core.models import Process, parse_json_to_process
from laminar.utils.image import encode_image_base64

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert business process analyst specializing in converting spreadsheet-based process descriptions into structured JSON representations.

Your task is to analyze business process data from Excel spreadsheets (provided as images and/or CSV data) and produce accurate, comprehensive JSON documents that capture every detail of the business process.

Key capabilities you should apply:
1. **Visual Analysis**: Carefully examine spreadsheet images to understand layout, relationships, and visual cues
2. **Data Extraction**: Parse CSV data to capture all textual information without losing any details
3. **Process Logic**: Identify the flow of steps, conditions, branches, and cycles in the process
4. **Role Mapping**: Associate each step with the appropriate role/actor
5. **Condition Detection**: Identify both explicit and implicit conditions that affect process flow

You must be extremely thorough - no single character of data from the source should be lost in the JSON output."""

ANALYSIS_PROMPT = """Analyze the provided business process data and generate a JSON description following the exact format of the sample JSON template.

## Critical Requirements:

### 1. Completeness
- Capture ALL data from the spreadsheet - every cell, note, and annotation
- Include all notes referenced in square brackets (e.g., [1], [2]) and match them to their definitions
- Preserve step descriptions, titles, and any metadata

### 2. Process Structure
- **SYSTEM::START**: Must be present and linked to the first actual step via `next_step`
- **SYSTEM::END**: Represents successful process completion - trace all success paths to this
- **SYSTEM::ABORT**: Represents premature termination due to failed conditions

### 3. Conditions (CONDITION:: prefix)
- Identify ALL decision points, including implicit ones hidden in descriptions
- Use `next_step_yes` and `next_step_no` for conditional branching
- Add `yes_when` and `no_when` explanations when the condition needs clarification
- Example: "Check credit rating" implies a condition with pass/fail outcomes

### 4. Role Assignment
- Every non-system step must have a `step_role` matching a defined role
- Ensure all roles referenced in steps are defined in `process_roles`

### 5. Unique Identifiers
- All step IDs must be unique
- Note: `step_id` and `CONDITION::step_id` would conflict - ensure uniqueness

### 6. Notes Handling
- Notes in square brackets like [1], [2] must be extracted from the notes section
- Match each note reference to its definition and add to the step's `step_notes` array

### Example Transformation:
Input: "BU[1] Onboards customer after checking CR[2], DSCR[3]..."
Notes: "[1]Business Unit [2]Credit Rating [3]Debt-service coverage Ratio"

This should create multiple steps:
- Check credit rating (with condition for pass/fail)
- Check DSCR (with condition for pass/fail)
- Onboard customer (only if all checks pass)

## Output Format:
Return ONLY valid JSON matching the sample template structure. No markdown formatting, no explanations - just the JSON object."""


class AIAnalysisError(Exception):
    """Raised when AI analysis fails."""


class AIAnalyzer:
    """Analyzes business process spreadsheets using Claude AI."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the AI analyzer.

        Args:
            settings: Application settings. Uses default if not provided.
        """
        self._settings = settings or get_settings()
        self._client: anthropic.Anthropic | None = None

    @property
    def client(self) -> anthropic.Anthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            api_key = self._settings.anthropic_api_key.get_secret_value()
            if not api_key or api_key == "<your key>":
                raise AIAnalysisError(
                    "Anthropic API key not configured. Set LAMINAR_ANTHROPIC_API_KEY "
                    "environment variable or create a .env file."
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def analyze_sheet(
        self,
        csv_data: str,
        sheet_name: str,
        image_path: Path | str | None = None,
        sample_json_path: Path | str | None = None,
        sample_image_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """Analyze a spreadsheet sheet and generate process JSON.

        Args:
            csv_data: CSV content of the sheet.
            sheet_name: Name of the sheet being analyzed.
            image_path: Path to the PNG image of the sheet (optional).
            sample_json_path: Path to sample JSON template.
            sample_image_path: Path to sample image.

        Returns:
            Dictionary containing the process description.

        Raises:
            AIAnalysisError: If analysis fails.
        """
        sample_json_path = Path(sample_json_path or self._settings.sample_json_path)
        sample_image_path = Path(sample_image_path or self._settings.sample_image_path)

        # Load sample JSON
        if not sample_json_path.exists():
            raise AIAnalysisError(f"Sample JSON not found: {sample_json_path}")
        sample_json_content = sample_json_path.read_text()

        # Build message content
        content = self._build_message_content(
            csv_data=csv_data,
            sheet_name=sheet_name,
            image_path=Path(image_path) if image_path else None,
            sample_image_path=sample_image_path,
            sample_json_content=sample_json_content,
        )

        logger.info("Analyzing sheet '%s' with Claude...", sheet_name)

        try:
            response = self.client.messages.create(
                model=self._settings.claude_model,
                max_tokens=self._settings.claude_max_tokens,
                temperature=self._settings.claude_temperature,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.APIError as e:
            logger.error("Anthropic API call failed: %s", e)
            raise AIAnalysisError(f"AI analysis failed: {e}") from e

        # Extract text response
        response_text = ""
        for block in response.content:
            if block.type == "text":
                response_text = block.text
                break

        if not response_text:
            raise AIAnalysisError("Claude returned empty response")

        # Parse JSON from response (handle potential markdown code blocks)
        json_str = self._extract_json(response_text)

        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response as JSON: %s", e)
            logger.debug("Response was: %s", response_text[:500])
            raise AIAnalysisError(f"Invalid JSON in Claude response: {e}") from e

        logger.debug("Successfully analyzed sheet '%s'", sheet_name)
        return result

    def analyze_sheet_to_process(
        self,
        csv_data: str,
        sheet_name: str,
        image_path: Path | str | None = None,
        sample_json_path: Path | str | None = None,
        sample_image_path: Path | str | None = None,
    ) -> Process:
        """Analyze a sheet and return a Process object.

        Args:
            csv_data: CSV content of the sheet.
            sheet_name: Name of the sheet being analyzed.
            image_path: Path to the PNG image of the sheet (optional).
            sample_json_path: Path to sample JSON template.
            sample_image_path: Path to sample image.

        Returns:
            Process object representing the business process.
        """
        json_data = self.analyze_sheet(
            csv_data=csv_data,
            sheet_name=sheet_name,
            image_path=image_path,
            sample_json_path=sample_json_path,
            sample_image_path=sample_image_path,
        )
        return parse_json_to_process(json_data)

    def _build_message_content(
        self,
        csv_data: str,
        sheet_name: str,
        image_path: Path | None,
        sample_image_path: Path,
        sample_json_content: str,
    ) -> list[dict[str, Any]]:
        """Build the message content for the Claude API call.

        Args:
            csv_data: CSV content of the sheet.
            sheet_name: Name of the sheet.
            image_path: Path to the sheet image (optional).
            sample_image_path: Path to sample image.
            sample_json_content: Content of sample JSON.

        Returns:
            List of content blocks for the message.
        """
        content: list[dict[str, Any]] = []

        # Add sample image showing desired output format
        if sample_image_path.exists():
            content.append({
                "type": "text",
                "text": "Here is a sample diagram showing the desired output format. This is for reference only and is unrelated to the business process you will analyze:",
            })
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self._get_media_type(sample_image_path),
                    "data": encode_image_base64(sample_image_path),
                },
            })

        # Add the actual spreadsheet image if available
        if image_path and image_path.exists():
            content.append({
                "type": "text",
                "text": f"Here is the image of the Excel sheet '{sheet_name}' to analyze:",
            })
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self._get_media_type(image_path),
                    "data": encode_image_base64(image_path),
                },
            })

        # Add CSV data
        content.append({
            "type": "text",
            "text": f"Here is the data from sheet '{sheet_name}' in CSV format:\n\n```csv\n{csv_data}\n```",
        })

        # Add sample JSON template
        content.append({
            "type": "text",
            "text": f"Use this JSON structure as your output template:\n\n```json\n{sample_json_content}\n```",
        })

        # Add analysis instructions
        content.append({
            "type": "text",
            "text": ANALYSIS_PROMPT,
        })

        return content

    def _get_media_type(self, path: Path) -> str:
        """Get the MIME type for an image file.

        Args:
            path: Path to the image file.

        Returns:
            MIME type string.
        """
        suffix = path.suffix.lower()
        media_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return media_types.get(suffix, "image/png")

    def _extract_json(self, text: str) -> str:
        """Extract JSON from response text, handling markdown code blocks.

        Args:
            text: Response text that may contain JSON.

        Returns:
            Extracted JSON string.
        """
        text = text.strip()

        # Try to extract from markdown code block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        # Assume the whole response is JSON
        return text

    def save_json_result(
        self,
        json_data: dict[str, Any],
        output_path: Path | str,
    ) -> None:
        """Save JSON analysis result to a file.

        Args:
            json_data: The JSON data to save.
            output_path: Path to save the file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(json_data, indent=2))
        logger.debug("Saved JSON to: %s", output_path)
