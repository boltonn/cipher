# Filetype names (matching filetyper's registry `name` field) this analytic
# can turn into page images: PDFs via pdfium, rasters via Pillow (+ pillow-heif).
# Icons, vector (svg), CAD/3D and medical formats are left out on purpose.
PDF_FILETYPES = frozenset({"pdf"})
IMAGE_FILETYPES = frozenset({"bmp", "gif", "heif", "jp2", "jpeg", "png", "psd", "qoi", "tga", "tiff", "webp"})
SUPPORTED_FILETYPES = PDF_FILETYPES | IMAGE_FILETYPES
