"""Docker utility functions for file conversion."""

import logging
import subprocess
from pathlib import Path

from laminar.config import get_settings

logger = logging.getLogger(__name__)


class DockerConversionError(Exception):
    """Raised when Docker conversion fails."""


class DockerConverter:
    """Handles Docker-based file conversions."""

    def __init__(self, image_name: str | None = None) -> None:
        """Initialize the Docker converter.

        Args:
            image_name: Docker image to use. Defaults to settings value.
        """
        self.image_name = image_name or get_settings().docker_image

    def convert_xlsx_to_images(
        self,
        xlsx_path: Path | str,
        output_dir: Path | str,
        *,
        timeout: int | None = 300,
    ) -> list[Path]:
        """Convert an XLSX file to PNG images using Docker.

        Args:
            xlsx_path: Path to the Excel file.
            output_dir: Directory to store output images.
            timeout: Timeout in seconds for Docker command.

        Returns:
            List of paths to generated PNG images.

        Raises:
            DockerConversionError: If the conversion fails.
            FileNotFoundError: If the input file doesn't exist.
        """
        xlsx_path = Path(xlsx_path).resolve()
        output_dir = Path(output_dir).resolve()

        if not xlsx_path.exists():
            raise FileNotFoundError(f"Excel file not found: {xlsx_path}")

        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{output_dir}:/output",
            "-v",
            f"{xlsx_path.parent}:/input",
            self.image_name,
            f"/input/{xlsx_path.name}",
            "/output",
        ]

        logger.debug("Running Docker command: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
            logger.debug("Docker stdout: %s", result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error("Docker conversion failed: %s", e.stderr)
            raise DockerConversionError(
                f"Failed to convert {xlsx_path.name}: {e.stderr}"
            ) from e
        except subprocess.TimeoutExpired as e:
            logger.error("Docker conversion timed out after %d seconds", timeout)
            raise DockerConversionError(
                f"Conversion timed out after {timeout} seconds"
            ) from e

        # Find generated PNG files
        png_files = sorted(output_dir.glob("*.png"), key=lambda p: p.name)
        logger.info("Generated %d PNG files from %s", len(png_files), xlsx_path.name)

        return png_files


def is_docker_available() -> bool:
    """Check if Docker is available and running.

    Returns:
        True if Docker is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
