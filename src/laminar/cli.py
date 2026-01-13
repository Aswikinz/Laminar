"""Command-line interface for Laminar."""

import argparse
import sys
from pathlib import Path

from laminar import __version__
from laminar.config import get_settings
from laminar.services.process_extractor import ProcessExtractor, ProcessExtractionError, extract_and_generate
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
  laminar process.xlsx                    # Auto-detect: template or AI
  laminar process.xlsx -o ./diagrams      # Specify output directory
  laminar process.xlsx --force-ai         # Always use AI (skip template)
  laminar process.xlsx --force-template   # Only use template (fail if not compliant)
  laminar process.xlsx --sheet "Sheet1"   # Process specific sheet
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
        "-s",
        "--sheet",
        type=str,
        default=None,
        help="Process specific sheet (default: all sheets)",
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

    # Extraction mode options
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--force-ai",
        action="store_true",
        help="Always use AI extraction (skip template parsing)",
    )
    mode_group.add_argument(
        "--force-template",
        action="store_true",
        help="Only use template parsing (fail if file doesn't match template)",
    )

    return parser


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

    if input_file.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
        logger.error("Invalid file type. Expected Excel file (.xlsx, .xlsm, .xls)")
        return 1

    # Determine output directory
    output_dir = args.output or get_settings().output_dir
    output_dir = Path(output_dir).resolve()

    logger.info("Processing: %s", input_file.name)
    logger.info("Output directory: %s", output_dir)

    if args.force_ai:
        logger.info("Mode: AI extraction (forced)")
    elif args.force_template:
        logger.info("Mode: Template parsing only")
    else:
        logger.info("Mode: Auto (template with AI fallback)")

    try:
        results = extract_and_generate(
            xlsx_path=input_file.resolve(),
            output_dir=output_dir,
            sheet_name=args.sheet,
            force_ai=args.force_ai,
        )

        # Print summary
        print()
        print("=" * 50)
        print("PROCESSING COMPLETE")
        print("=" * 50)

        for sheet_result in results["sheets"]:
            sheet = sheet_result["sheet"]
            if sheet_result.get("success"):
                method = sheet_result.get("metadata", {}).get("method", "unknown")
                confidence = sheet_result.get("metadata", {}).get("confidence", 0) * 100
                print(f"  [OK] {sheet}")
                print(f"       Method: {method} ({confidence:.0f}% confidence)")
                print(f"       -> {sheet_result.get('mermaid_path', 'N/A')}")
            else:
                print(f"  [FAIL] {sheet}")
                print(f"       Error: {sheet_result.get('error', 'Unknown error')}")

        print()

        if results["success"]:
            logger.info("All sheets processed successfully!")
            return 0
        else:
            logger.warning("Some sheets failed to process")
            return 1

    except ProcessExtractionError as e:
        logger.error("Extraction failed: %s", e)
        return 2
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return 3


if __name__ == "__main__":
    sys.exit(main())
