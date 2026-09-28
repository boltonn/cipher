import contextlib
import re
from datetime import datetime
from typing import Any, TypedDict

import chardet
from loguru import logger
from PIL import Image, TiffTags
from PIL.ExifTags import GPSTAGS, IFD, TAGS

# Ensure pillow-heif is installed for HEIC support
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    logger.warning("pillow-heif not installed. HEIC support will be limited.")


class ExifMetadata(TypedDict, total=False):
    camera_make: str
    camera_model: str
    lens_model: str
    focal_length: float
    aperture: float
    iso: int
    shutter_speed: str
    orientation: int
    date_taken: datetime
    gps_latitude: float
    gps_longitude: float
    gps_altitude: float
    gps_bearing: int
    gps_speed: float
    gps_h_accuracy: float


class ImageMetadataExtractor:
    """Universal extractor for JPEG, TIFF, HEIC, and XMP/IPTC data."""

    _CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

    @staticmethod
    def extract_metadata(img: Image.Image) -> ExifMetadata | None:
        """Extract metadata from all possible internal sources."""
        full_data = {}

        # --- 1. EXIF SOURCE (Standard for JPEG/HEIC) ---
        raw_exif = img.getexif()
        if raw_exif:
            for ifd_id in IFD:
                with contextlib.suppress(Exception):
                    ifd_data = raw_exif.get_ifd(ifd_id)
                    for tag_id, value in ifd_data.items():
                        name = GPSTAGS.get(tag_id, tag_id) if ifd_id == IFD.GPSInfo else TAGS.get(tag_id, tag_id)
                        full_data[str(name)] = ImageMetadataExtractor._ensure_json_safe(value)

            for tag_id, value in raw_exif.items():
                name = TAGS.get(tag_id, tag_id)
                if str(name) not in full_data:
                    full_data[str(name)] = ImageMetadataExtractor._ensure_json_safe(value)

        # --- 2. TIFF SOURCE (V1 and V2 Tags) ---
        # tag_v2 is cleaner, img.tag (v1) is more compatible with old scanners
        for attr in ["tag_v2", "tag"]:
            if hasattr(img, attr):
                tag_dict = getattr(img, attr)
                for tag_id, value in tag_dict.items():
                    tag_info = TiffTags.TAGS_V2.get(tag_id) or TiffTags.TAGS_V1.get(tag_id)
                    name = tag_info.name if tag_info else str(tag_id)
                    if name not in full_data or full_data[name] in [None, "", []]:
                        full_data[name] = ImageMetadataExtractor._ensure_json_safe(value)

        # --- 3. LAST RESORT: INFO DICTIONARY (XMP/IPTC) ---
        # Adobe often hides metadata in XMP strings or raw IPTC blocks
        if hasattr(img, "info"):
            if "xmp" in img.info:
                # Store raw XMP for possible specialized parsing later
                full_data["XMP_Block"] = ImageMetadataExtractor._ensure_json_safe(img.info["xmp"])
            if "iptc" in img.info:
                full_data["IPTC_Block"] = ImageMetadataExtractor._ensure_json_safe(img.info["iptc"])

        if not full_data:
            return None

        return ImageMetadataExtractor._map_to_schema(full_data)

    @staticmethod
    def _ensure_json_safe(value: Any) -> Any:
        """Recursively unpacks tuples and cleans non-printable characters."""
        # Unpack TIFF-style single-element tuples (e.g. ('Apple',))
        if isinstance(value, (tuple, list)) and len(value) == 1:
            return ImageMetadataExtractor._ensure_json_safe(value[0])

        # Handle PIL Rational types
        if hasattr(value, "numerator"):
            try:
                return float(value)
            except ZeroDivisionError:
                return 0.0

        if isinstance(value, (tuple, list)):
            return [ImageMetadataExtractor._ensure_json_safe(v) for v in value]

        if isinstance(value, dict):
            return {str(k): ImageMetadataExtractor._ensure_json_safe(v) for k, v in value.items()}

        if isinstance(value, bytes):
            try:
                # Smart decoding with chardet for International support
                result = chardet.detect(value)
                encoding = result["encoding"] or "utf-8"
                value = value.decode(encoding, errors="ignore")
            except Exception:
                value = value.decode("utf-8", errors="ignore")

        if isinstance(value, str):
            # Strip \x00, \x03 and all other invisible control characters
            value = ImageMetadataExtractor._CONTROL_CHAR_RE.sub("", value).strip()

        return value

    @staticmethod
    def _map_to_schema(data: dict) -> ExifMetadata:
        """Standardizes disparate keys into a common schema."""
        results = {}
        field_map = {
            "Make": "camera_make",
            "Model": "camera_model",
            "LensModel": "lens_model",
            "FocalLength": "focal_length",
            "FNumber": "aperture",
            "ISOSpeedRatings": "iso",
            "ExposureTime": "shutter_speed",
            "Orientation": "orientation",
            "DateTime": "date_taken",  # TIFF often uses 'DateTime'
            "DateTimeOriginal": "date_taken",
        }

        for exif_key, target_key in field_map.items():
            if exif_key in data:
                results[target_key] = data[exif_key]

        # Standardize Date objects
        dt_val = results.get("date_taken")
        if dt_val and isinstance(dt_val, str):
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                with contextlib.suppress(Exception):
                    results["date_taken"] = datetime.strptime(dt_val, fmt)
                    break

        # ISO normalization - could be mapped
        iso_val = results.get("iso")
        if iso_val is not None:
            try:
                iso_float = float(iso_val)

                # Round to nearest standard ISO
                results["iso"] = int(round(iso_float))
            except Exception:
                results.pop("iso", None)

        if "GPSLatitude" in data and "GPSLatitudeRef" in data:
            results["gps_latitude"] = ImageMetadataExtractor._parse_coord(data["GPSLatitude"], data["GPSLatitudeRef"])
        if "GPSLongitude" in data and "GPSLongitudeRef" in data:
            results["gps_longitude"] = ImageMetadataExtractor._parse_coord(
                data["GPSLongitude"], data["GPSLongitudeRef"]
            )

        # Altitude: HEIC/TIFF often return different types here
        if "GPSAltitude" in data:
            with contextlib.suppress(Exception):
                alt = float(data["GPSAltitude"])
                ref = data.get("GPSAltitudeRef")
                # 1 usually means below sea level in EXIF
                if ref == 1 or ref == b"\x01":
                    alt = -alt
                results["gps_altitude"] = alt

        # Heading, ground speed, and positional accuracy (kinematics)
        if "GPSImgDirection" in data:
            with contextlib.suppress(Exception):
                results["gps_bearing"] = int(round(float(data["GPSImgDirection"]))) % 360
        if "GPSSpeed" in data:
            with contextlib.suppress(Exception):
                ref = data.get("GPSSpeedRef")
                # K = km/h (EXIF default), M = mph, N = knots -> m/s
                factor = {"K": 1 / 3.6, "M": 0.44704, "N": 0.514444}.get(ref, 1 / 3.6)
                results["gps_speed"] = float(data["GPSSpeed"]) * factor
        if "GPSHPositioningError" in data:
            with contextlib.suppress(Exception):
                results["gps_h_accuracy"] = float(data["GPSHPositioningError"])

        return results

    @staticmethod
    def _parse_coord(value: Any, ref: str) -> float | None:
        try:
            # Handles both standard [d, m, s] and single-float coordinates
            if isinstance(value, (list, tuple)):
                d, m, s = [float(x) for x in value]
                decimal = d + (m / 60.0) + (s / 3600.0)
            else:
                decimal = float(value)

            if ref in ["S", "W"]:
                decimal = -decimal
            return decimal
        except Exception:
            return None
