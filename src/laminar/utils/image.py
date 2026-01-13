"""Image utility functions."""

import base64
from pathlib import Path


def encode_image_base64(image_path: Path | str) -> str:
    """Encode an image file to base64 string.

    Args:
        image_path: Path to the image file.

    Returns:
        Base64-encoded string of the image contents.

    Raises:
        FileNotFoundError: If the image file doesn't exist.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    return base64.b64encode(path.read_bytes()).decode("utf-8")


def get_image_data_url(image_path: Path | str, media_type: str = "image/png") -> str:
    """Get a data URL for an image file.

    Args:
        image_path: Path to the image file.
        media_type: MIME type of the image.

    Returns:
        Data URL string for the image.
    """
    encoded = encode_image_base64(image_path)
    return f"data:{media_type};base64,{encoded}"
