# isort: skip_file
from __future__ import annotations

# Import all models that have 'table=True'
##### WARNING: CAREFUL WHEN EDITING #####
##### ORDER OF IMPORTS MATTERS FOR TABLE DEPENDENCIES #####
from cipher.datastores.postgres.tables.file import FileTable
from cipher.datastores.postgres.tables.dataset import DatasetTable
from cipher.datastores.postgres.tables.enrichment import EnrichmentTable
from cipher.datastores.postgres.tables.image import ImageTable
from cipher.datastores.postgres.tables.extracted_text import ExtractedTextTable
from cipher.datastores.postgres.tables.device import DeviceTable
from cipher.datastores.postgres.tables.message import MessageTable
from cipher.datastores.postgres.tables.contact import ContactTable
from cipher.datastores.postgres.tables.user import UserTable
from cipher.datastores.postgres.tables.person import PersonTable
from cipher.datastores.postgres.tables.face import FaceTable
from cipher.datastores.postgres.tables.face_match import FaceMatchTable

__all__ = [
    "FileTable",
    "DatasetTable",
    "EnrichmentTable",
    "ImageTable",
    "ExtractedTextTable",
    "DeviceTable",
    "MessageTable",
    "ContactTable",
    "UserTable",
    "PersonTable",
    "FaceTable",
    "FaceMatchTable",
]
