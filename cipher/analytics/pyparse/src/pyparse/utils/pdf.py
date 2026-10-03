import shutil
import struct
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Literal

from loguru import logger
from pdfminer.jbig2 import JBIG2StreamReader, JBIG2StreamWriter
from pdfminer.layout import LTImage
from pdfminer.pdfcolor import (
    LITERAL_DEVICE_CMYK,
    LITERAL_DEVICE_GRAY,
    LITERAL_DEVICE_RGB,
)
from pdfminer.pdftypes import (
    LITERALS_DCT_DECODE,
    LITERALS_FLATE_DECODE,
    LITERALS_JBIG2_DECODE,
    LITERALS_JPX_DECODE,
)
from PIL import Image, ImageChops, ImageFile, ImageOps
from pyparse.parsers.base import get_file_instance
from pyparse.schemas.data import Image as ImageSchema
from pyparse.schemas.enums import FileType
from pyparse.utils.general import get_hashes

ImageFile.LOAD_TRUNCATED_IMAGES = True

# TODO: file output should be hash but the have to figure out how to get BMP to work


def align32(x: int) -> int:
    """Align to 4 bytes."""
    return ((x + 3) // 4) * 4


class BMPWriter:
    def __init__(self, fp: BytesIO, width: int, height: int, bits: int = 8) -> None:
        self.fp = fp
        self.width = width
        self.height = height
        self.bits = bits

        if bits == 1:
            self.colors = 2
        elif bits == 8:
            self.colors = 256
        elif bits == 24:
            self.colors = 0
        else:
            raise ValueError(f"Invalid bits: {bits}")

        self.line_size = align32((self.width * self.bits + 7) // 8)
        self.image_size = self.line_size * self.height
        header_size = 14 + 40 + self.colors * 4
        info = struct.pack(
            "<IiiHHIIIIII",
            40,
            self.width,
            self.height,
            1,
            self.bits,
            0,
            self.image_size,
            0,
            0,
            self.colors,
            0,
        )
        assert len(info) == 40, len(info)
        header = struct.pack("<ccIHHI", b"B", b"M", header_size + self.image_size, 0, 0, header_size)
        assert len(header) == 14, len(header)
        self.fp.write(header + info)
        if self.colors == 2:
            # black and white
            for i in (0, 255):
                self.fp.write(struct.pack("<BBBx", i, i, i))
        elif self.colors == 256:
            # grayscale
            for i in range(256):
                self.fp.write(struct.pack("BBBx", i, i, i))
        elif self.colors == 0:
            pass
        else:
            raise ValueError(f"Invalid colors: {self.colors}")

        self.pos0 = self.fp.tell()
        self.pos1 = self.pos0 + self.image_size

    def write_line(self, y: int, data: bytes) -> None:
        self.fp.seek(self.pos1 - (y + 1) * self.line_size)
        self.fp.write(data)


class PDFImageHandler:
    """A fork of pdfminer's PDFImageHandler that supports writing to disk."""

    def __init__(self, extract_children: bool = True, out_dir: Path = None) -> None:
        # starter for writing out files
        self.i = 0
        self.extract_children = extract_children
        if self.extract_children:
            assert out_dir is not None, "Must provide an output directory if extract_children is True"
            self.out_dir = out_dir
            self.out_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Extracting images to {self.out_dir}")

    def handle_image(self, image: LTImage) -> ImageSchema:
        """Save an image to disk."""
        (height, width) = image.srcsize
        meta = {"height": height, "width": width, "file_type": FileType.image}

        filters = image.stream.get_filters()

        if len(filters) == 1 and filters[0][0] in LITERALS_DCT_DECODE:
            meta = self._parse_jpeg(meta=meta, image=image)
        elif len(filters) == 1 and filters[0][0] in LITERALS_JPX_DECODE:
            meta = self._parse_jpeg2000(meta=meta, image=image)
        elif self._is_jbig2(image):
            meta = self._parse_jbig2(meta=meta, image=image)
        elif image.bits == 1:
            meta = self._parse_bmp(
                meta=meta,
                image=image,
                width=width,
                height=height,
                bytes_per_line=(width + 7) // 8,
                bits=1,
            )
        elif image.bits == 8 and LITERAL_DEVICE_RGB in image.colorspace:
            meta = self._parse_bmp(
                meta=meta,
                image=image,
                width=width,
                height=height,
                bytes_per_line=width * 3,
                bits=image.bits * 3,
            )
        elif image.bits == 8 and LITERAL_DEVICE_GRAY in image.colorspace:
            meta = self._parse_bmp(
                meta=meta,
                image=image,
                width=width,
                height=height,
                bytes_per_line=width,
                bits=image.bits,
            )
        elif len(filters) == 1 and filters[0][0] in LITERALS_FLATE_DECODE:
            meta = self._parse_bytes(meta=meta, image=image)
        else:
            meta = self._parse_raw(meta=meta, image=image)

        return ImageSchema(**meta)

    def _parse_jpeg(self, meta: dict, image: LTImage) -> dict:
        """Parse a JPEG image."""
        raw_data = image.stream.get_data()
        assert raw_data is not None, "JPEG image has no data"

        file_ext = ".jpg"
        meta["mime_type"] = "image/jpeg"

        img = Image.open(BytesIO(raw_data))
        if LITERAL_DEVICE_CMYK in image.colorspace:
            # CMYK -> RGB
            img = ImageChops.invert(img)

        img = img.convert("RGB")
        meta |= get_file_instance(img.tobytes())
        if self.extract_children:
            out_file_name = meta["hash"]["md5"] + file_ext
            file_path = self.out_dir / out_file_name
            img.save(file_path, "JPEG")
            logger.info(f"Saved image to {file_path}")
            meta |= {"file_extension": file_ext, "path": file_path}

        return meta

    def _parse_jpeg2000(self, meta: dict, image: LTImage) -> dict:
        """Parse a JPEG2000 image."""
        raw_data = image.stream.get_data()
        assert raw_data is not None, "JPEG2000 image has no data"
        meta |= get_file_instance(raw_data)
        meta["mime_type"] = "image/jp2"

        file_ext = ".jp2"

        img = Image.open(BytesIO(raw_data))

        if self.extract_children:
            out_file_name = meta["hash"]["md5"] + file_ext
            file_path = self.out_dir / out_file_name
            img.save(file_path, "JPEG2000")
            logger.info(f"Saved image to {file_path}")
            meta |= {"file_extension": file_ext, "path": file_path}

        return meta

    def _parse_jbig2(self, meta: dict, image: LTImage) -> dict:
        """Parse a JBIG2 image."""
        file_ext = ".jb2"
        meta["mime_type"] = "image/x-jbig2"
        input_stream = BytesIO()

        global_streams = []
        filters = image.stream.get_filters()
        for filter_type, params in filters:
            if filter_type == LITERALS_JBIG2_DECODE:
                global_streams.append(params["JBIG2Globals"].resolve())

        if len(global_streams) > 1:
            raise ValueError("Cannot handle multiple JBIG2 global streams")
        elif len(global_streams) == 1:
            global_stream_data = global_streams[0].get_data().rstrip(b"\n")
            input_stream.write(global_stream_data)
        input_stream.write(image.stream.get_data())
        input_stream.seek(0)
        reader = JBIG2StreamReader(input_stream)
        segments = reader.get_segments()

        if self.extract_children:
            with tempfile.NamedTemporaryFile() as tmp:
                writer = JBIG2StreamWriter(tmp)
                writer.write_file(segments)
                tmp.seek(0)
                meta |= {
                    "hash": get_hashes(tmp.read()),
                    "file_extension": file_ext,
                }
                out_path = self.out_dir / (meta["hash"]["md5"] + file_ext)
                # copy temp file to output directory
                shutil.copyfile(tmp.name, out_path)
                logger.info(f"Saved image to {out_path}")
                meta |= {"path": out_path}
        return meta

    def _parse_bmp(
        self,
        meta: dict,
        image: LTImage,
        width: int,
        height: int,
        bytes_per_line: int,
        bits: int,
    ) -> dict:
        """Parse a BMP image."""
        file_ext = ".bmp"
        meta["mime_type"] = "image/bmp"

        if self.extract_children:
            with tempfile.NamedTemporaryFile() as tmp:
                writer = BMPWriter(tmp, bits=bits, width=width, height=height)
                data = image.stream.get_data()
                for i in range(height):
                    writer.write_line(i, data[i : i + bytes_per_line])  # noqa E203
                    i += bytes_per_line
                meta["hash"] = get_hashes(tmp.name)
                file_path = self.out_dir / (meta["hash"]["md5"] + file_ext)
                shutil.copyfile(tmp.name, file_path)
                logger.info(f"Saved image to {file_path}")
                meta |= {"file_extension": file_ext, "path": file_path}

        return meta

    def _parse_bytes(self, meta: dict, image: LTImage) -> dict:
        """Parse a bytes image."""
        file_ext = ".jpg"
        width, height = image.srcsize
        channels = len(image.stream.get_data()) / (width * height * (image.bits / 8))

        mode: Literal["1", "L", "RGB", "CMYK"]
        if image.bits == 1:
            mode = "1"
        elif image.bits == 8 and channels == 1:
            mode = "L"
        elif image.bits == 8 and channels == 3:
            mode = "RGB"
        elif image.bits == 8 and channels == 4:
            mode = "CMYK"

        img = Image.frombytes(
            mode=mode,
            size=(width, height),
            data=image.stream.get_data(),
            decoder_name="raw",
        )
        if mode == "L":
            img = ImageOps.invert(img)

        meta |= get_file_instance(img.tobytes())

        if self.extract_children:
            file_path = self.out_dir / (meta["hash"]["md5"] + file_ext)
            img.save(file_path, "JPEG")
            logger.info(f"Saved image to {file_path}")
            meta |= {
                "file_extension": file_ext,
                "path": file_path,
                "mime_type": "image/jpeg",
            }

        return meta

    def _parse_raw(self, meta: dict, image: LTImage) -> dict:
        """Parse a raw image with unknown encoding."""
        file_ext = ".bin"

        raw_data = image.stream.get_data()
        meta |= get_file_instance(raw_data)

        if self.extract_children:
            file_path = self.out_dir / (meta["hash"]["md5"] + file_ext)
            with open(file_path, "wb") as fb:
                fb.write(raw_data)
            logger.info(f"Saved image to {file_path}")
            meta |= {"file_extension": file_ext, "path": file_path}

        return meta

    @staticmethod
    def _is_jbig2(image: LTImage) -> bool:
        """Check if an image is a JBIG2 image."""
        filters = image.stream.get_filters()
        return any(filter_type == LITERALS_JBIG2_DECODE for filter_type, _ in filters)
