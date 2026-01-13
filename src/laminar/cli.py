"""Command-line interface for Laminar."""

import argparse
import json
import sys
from pathlib import Path

from laminar import __version__
from laminar.config import get_settings
from laminar.core.models import parse_json_to_process
from laminar.services.ai_analyzer import AIAnalyzer, AIAnalysisError
from laminar.services.excel_processor import ExcelProcessor, ExcelProcessingError
from laminar.services.mermaid_generator import generate_mermaid_from_process, save_mermaid_chart
from laminar.utils.docker import DockerConverter, DockerConversionError, is_docker_available
from laminar.utils.logging import setup_logging, get_logger

logger = get_logger("cli")


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="laminar",
        description="Convert Excel business process spreadsheets to Mermaid flowcharts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  laminar process.xlsx
  laminar process.xlsx -o ./diagrams
  laminar process.xlsx --verbose
        """,
    )

    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to the Excel file to process",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: ./output)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "--skip-docker-check",
        action="store_true",
        help="Skip Docker availability check",
    )

    return parser


def process_excel_file(
    input_file: Path,
    output_dir: Path,
    *,
    verbose: bool = False,
) -> int:
    """Process an Excel file and generate Mermaid diagrams.

    Args:
        input_file: Path to the Excel file.
        output_dir: Directory for output files.
        verbose: Enable verbose logging.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    settings = get_settings()

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Initialize services
    docker_converter = DockerConverter()
    excel_processor = ExcelProcessor()
    ai_analyzer = AIAnalyzer()

    try:
        # Convert XLSX to images
        logger.info("Converting Excel file to images...")
        png_files = docker_converter.convert_xlsx_to_images(input_file, temp_dir)

        # Extract CSV data
        logger.info("Extracting sheet data...")
        csv_data = excel_processor.extract_sheets_as_csv(input_file, temp_dir)

        logger.info("Found %d sheets: %s", len(csv_data), ", ".join(csv_data.keys()))

        # Process each sheet
        for idx, (sheet_name, csv_content) in enumerate(csv_data.items()):
            if idx >= len(png_files):
                logger.warning(
                    "No image found for sheet '%s', skipping", sheet_name
                )
                continue

            logger.info("Processing sheet: %s", sheet_name)

            # Analyze with AI
            json_result = ai_analyzer.analyze_sheet(
                csv_data=csv_content,
                sheet_name=sheet_name,
                image_path=png_files[idx],
            )

            # Save intermediate JSON
            json_path = output_dir / f"{sheet_name}_description.json"
            json_path.write_text(json.dumps(json_result, indent=2))

            # Generate Mermaid diagram
            process = parse_json_to_process(json_result)
            mermaid_chart = generate_mermaid_from_process(process)

            # Save Mermaid chart
            mermaid_path = output_dir / f"{sheet_name}_flowchart.mmd"
            save_mermaid_chart(mermaid_chart, mermaid_path)

            logger.info("Generated: %s", mermaid_path)

        logger.info("Processing complete! Output saved to: %s", output_dir)
        return 0

    except DockerConversionError as e:
        logger.error("Docker conversion failed: %s", e)
        return 1
    except ExcelProcessingError as e:
        logger.error("Excel processing failed: %s", e)
        return 2
    except AIAnalysisError as e:
        logger.error("AI analysis failed: %s", e)
        return 3
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return 4


def main() -> int:
    """Main entry point for the CLI.

    Returns:
        Exit code.
    """
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level)

    # Validate input file
    input_file: Path = args.input_file
    if not input_file.exists():
        logger.error("Input file not found: %s", input_file)
        return 1

    if not input_file.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        logger.error("Invalid file type. Expected Excel file (.xlsx, .xlsm, .xls)")
        return 1

    # Check Docker availability
    if not args.skip_docker_check and not is_docker_available():
        logger.error(
            "Docker is not available. Please install Docker and ensure it's running."
        )
        return 1

    # Determine output directory
    output_dir = args.output or get_settings().output_dir
    output_dir = Path(output_dir).resolve()

    return process_excel_file(
        input_file=input_file.resolve(),
        output_dir=output_dir,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
