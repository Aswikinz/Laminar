"""AI-powered business process analysis service."""

import json
import logging
from pathlib import Path
from typing import Any

from openai import OpenAI

from laminar.config import Settings, get_settings
from laminar.core.models import Process, parse_json_to_process
from laminar.utils.image import get_image_data_url

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are business process analyzer which is analyzing business process description in the form of spreadsheet based on visual representation of the spreadsheet and CSV-formatted extract. Based on this data you are producing a JSON document with description of the business process"""

ANALYSIS_INSTRUCTIONS = """Generate a JSON description for a diagram based on the provided data and images, ensuring it matches the format of the sample JSON. Make sure that notes for each process step are appended to according notes array in JSON output. An important criteria is to make sure no single character of data from the Excel spreadsheet is lost when we generate the JSON representation of the business process. Make sure to analyze the logic of the process, linking between the steps and especially CONDITIONS and CYCLES which occur in the business process. Add CONDITION:: blocks as in sample.json. Pay attention: conditions may be implicitly present in the process description, understand the underlying logic and introduce necessary conditions.

Remember that conditions may require additional explication. "yes_when" and "no_when" blocks must not be added for simple yes/no questions but make sure to add them in case the condition is requiring some details.

Determine process start and end. SYSTEM::START and SYSTEM::END are obligatory items. SYSTEM::START must be linked to the first actual step in the process, so it MUST have the next_step provided. Make sure to find all steps that lead to process finish and trace them to SYSTEM::END. Carefully analyze process descriptions. There can be implicitly multiple steps with their own steps and conditions hidden there. There can be notes referred in square brackets in notes section, so you should properly pick up notes from their row and assign to their rightful process steps.

For example, this description: "BU[1] Onboards the customer after cheeking CR[2],DSCR[3] income, Client Vehicle and Handles CIF[4] creation and support document[5] submission" must be matched with these notes [1]Business Unit.
[2]Credit Rating.
[3] Debt-service coverage Ratio.
[4]Client Information File.
[5]support documents include: salary slips, bank statements, documents relating to the vehicle and other documents depending on the requirement.

and this would unfold into defining several independent process steps within the JSON file: check credit rating; check debt-service coverage ratio, check client income, with conditions to terminate the process in case any check fails

Make sure to properly distinguish between SYSTEM::END and SYSTEM::ABORT - while END is a successful completion of the business process, ABORT means abrupt termination due to certain condition

Make sure to have all roles and step identifiers unique. For example, step_identifier and CONDITION::step_identifier are the same."""


class AIAnalysisError(Exception):
    """Raised when AI analysis fails."""


class AIAnalyzer:
    """Analyzes business process spreadsheets using AI."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the AI analyzer.

        Args:
            settings: Application settings. Uses default if not provided.
        """
        self._settings = settings or get_settings()
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            api_key = self._settings.openai_api_key.get_secret_value()
            if not api_key or api_key == "<your key>":
                raise AIAnalysisError(
                    "OpenAI API key not configured. Set LAMINAR_OPENAI_API_KEY "
                    "environment variable or create a .env file."
                )
            self._client = OpenAI(api_key=api_key)
        return self._client

    def analyze_sheet(
        self,
        csv_data: str,
        sheet_name: str,
        image_path: Path | str,
        sample_json_path: Path | str | None = None,
        sample_image_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """Analyze a spreadsheet sheet and generate process JSON.

        Args:
            csv_data: CSV content of the sheet.
            sheet_name: Name of the sheet being analyzed.
            image_path: Path to the PNG image of the sheet.
            sample_json_path: Path to sample JSON template.
            sample_image_path: Path to sample image.

        Returns:
            Dictionary containing the process description.

        Raises:
            AIAnalysisError: If analysis fails.
        """
        sample_json_path = sample_json_path or self._settings.sample_json_path
        sample_image_path = sample_image_path or self._settings.sample_image_path

        image_path = Path(image_path)
        sample_json_path = Path(sample_json_path)
        sample_image_path = Path(sample_image_path)

        # Load sample JSON
        if not sample_json_path.exists():
            raise AIAnalysisError(f"Sample JSON not found: {sample_json_path}")
        sample_json_content = sample_json_path.read_text()

        # Build messages
        messages = self._build_messages(
            csv_data=csv_data,
            sheet_name=sheet_name,
            image_path=image_path,
            sample_image_path=sample_image_path,
            sample_json_content=sample_json_content,
        )

        logger.info("Analyzing sheet '%s' with AI...", sheet_name)

        try:
            response = self.client.chat.completions.create(
                model=self._settings.openai_model,
                messages=messages,
                temperature=self._settings.openai_temperature,
                max_tokens=self._settings.openai_max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            logger.error("OpenAI API call failed: %s", e)
            raise AIAnalysisError(f"AI analysis failed: {e}") from e

        content = response.choices[0].message.content
        if not content:
            raise AIAnalysisError("AI returned empty response")

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse AI response as JSON: %s", e)
            raise AIAnalysisError(f"Invalid JSON in AI response: {e}") from e

        logger.debug("Successfully analyzed sheet '%s'", sheet_name)
        return result

    def analyze_sheet_to_process(
        self,
        csv_data: str,
        sheet_name: str,
        image_path: Path | str,
        sample_json_path: Path | str | None = None,
        sample_image_path: Path | str | None = None,
    ) -> Process:
        """Analyze a sheet and return a Process object.

        Args:
            csv_data: CSV content of the sheet.
            sheet_name: Name of the sheet being analyzed.
            image_path: Path to the PNG image of the sheet.
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

    def _build_messages(
        self,
        csv_data: str,
        sheet_name: str,
        image_path: Path,
        sample_image_path: Path,
        sample_json_content: str,
    ) -> list[dict[str, Any]]:
        """Build the message list for the OpenAI API call.

        Args:
            csv_data: CSV content of the sheet.
            sheet_name: Name of the sheet.
            image_path: Path to the sheet image.
            sample_image_path: Path to sample image.
            sample_json_content: Content of sample JSON.

        Returns:
            List of message dictionaries.
        """
        sample_image_url = get_image_data_url(sample_image_path)
        sheet_image_url = get_image_data_url(image_path)

        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Here is the sample image which reflects what kind of diagram "
                    "what we will build. This image is only for information purposes "
                    "and not related to the particular business processes that we will handle."
                ),
            },
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": sample_image_url}}],
            },
            {
                "role": "user",
                "content": f"Here is the image for analysis from sheet {sheet_name}:",
            },
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": sheet_image_url}}],
            },
            {
                "role": "user",
                "content": (
                    f"Here is the data from sheet {sheet_name} in CSV format:\n{csv_data}"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Use the following JSON format as a template for generating the "
                    "JSON description of the diagram. Remember that JSON sample has "
                    "nothing in common with the business process we are working with, "
                    "except the data format."
                ),
            },
            {"role": "user", "content": sample_json_content},
            {"role": "user", "content": ANALYSIS_INSTRUCTIONS},
        ]

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
