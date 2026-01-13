"""Excel file processing service."""

import logging
from io import StringIO
from pathlib import Path

import pandas as pd

from laminar.core.constants import MISSING_VALUE_PLACEHOLDER

logger = logging.getLogger(__name__)


class ExcelProcessingError(Exception):
    """Raised when Excel processing fails."""


class ExcelProcessor:
    """Handles Excel file reading and CSV extraction."""

    def __init__(self, placeholder: str = MISSING_VALUE_PLACEHOLDER) -> None:
        """Initialize the Excel processor.

        Args:
            placeholder: Value to use for missing data.
        """
        self.placeholder = placeholder

    def extract_sheets_as_csv(
        self,
        xlsx_path: Path | str,
        output_dir: Path | str | None = None,
    ) -> dict[str, str]:
        """Extract all sheets from an Excel file as CSV strings.

        Args:
            xlsx_path: Path to the Excel file.
            output_dir: Optional directory to save CSV files.

        Returns:
            Dictionary mapping sheet names to CSV content strings.

        Raises:
            ExcelProcessingError: If processing fails.
            FileNotFoundError: If the file doesn't exist.
        """
        xlsx_path = Path(xlsx_path)
        if not xlsx_path.exists():
            raise FileNotFoundError(f"Excel file not found: {xlsx_path}")

        if output_dir is not None:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        try:
            xls = pd.ExcelFile(xlsx_path)
        except Exception as e:
            raise ExcelProcessingError(f"Failed to open Excel file: {e}") from e

        csv_data: dict[str, str] = {}

        for sheet_name in xls.sheet_names:
            logger.debug("Processing sheet: %s", sheet_name)

            try:
                df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
                df = self._clean_dataframe(df)

                csv_buffer = StringIO()
                df.to_csv(csv_buffer, index=False, sep=";")
                csv_content = csv_buffer.getvalue()

                csv_data[sheet_name] = csv_content

                if output_dir is not None:
                    csv_path = output_dir / f"{sheet_name}.csv"
                    csv_path.write_text(csv_content)
                    logger.debug("Saved CSV to: %s", csv_path)

            except Exception as e:
                logger.error("Failed to process sheet %s: %s", sheet_name, e)
                raise ExcelProcessingError(
                    f"Failed to process sheet '{sheet_name}': {e}"
                ) from e

        logger.info(
            "Extracted %d sheets from %s: %s",
            len(csv_data),
            xlsx_path.name,
            ", ".join(csv_data.keys()),
        )

        return csv_data

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean a DataFrame for CSV export.

        Args:
            df: The DataFrame to clean.

        Returns:
            Cleaned DataFrame.
        """
        # Fill missing values
        df = df.fillna(self.placeholder)

        # Clean up column names
        df.columns = pd.Index([
            col if not str(col).startswith("Unnamed:") else self.placeholder
            for col in df.columns
        ])

        # Replace semicolons in string values to avoid CSV delimiter conflicts
        df = df.map(
            lambda x: str(x).replace(";", ",") if isinstance(x, str) else x
        )

        return df

    def get_sheet_names(self, xlsx_path: Path | str) -> list[str]:
        """Get the names of all sheets in an Excel file.

        Args:
            xlsx_path: Path to the Excel file.

        Returns:
            List of sheet names.

        Raises:
            FileNotFoundError: If the file doesn't exist.
        """
        xlsx_path = Path(xlsx_path)
        if not xlsx_path.exists():
            raise FileNotFoundError(f"Excel file not found: {xlsx_path}")

        xls = pd.ExcelFile(xlsx_path)
        return list(xls.sheet_names)
