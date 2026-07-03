import docx
import docx.table
import pptx
from tabulate import tabulate

METADATA_MAPPINGS = {
    "author": "created_by",
    "comments": "comments",
    "created": "date_created",
    "keywords": "keywords",
    "last_modified_by": "modified_by",
    "modified": "date_modified",
    "revision": "revision",
    "subject": "subject",
    "title": "title",
    "version": "version",
}


def parse_meta(
    doc: docx.document.Document | pptx.presentation.Presentation, raw: bool = False
) -> dict:
    """Parse the metadata from a Microsoft Office document."""
    meta = {
        att: getattr(doc.core_properties, att)
        for att in dir(doc.core_properties)
        if not att.startswith("_")
    }
    return (
        {
            METADATA_MAPPINGS[k]: v
            for k, v in meta.items()
            if k in METADATA_MAPPINGS and v
        }
        if raw is False
        else meta
    )


def get_visual_cells(row):
    """Get the visual cells from a row, accounting for merged cells."""
    prior_tc = None
    for cell in row.cells:
        tc = cell._tc
        if prior_tc is not None:
            if prior_tc is tc:
                continue
            else:
                prior_tc = tc
                yield cell
        else:
            prior_tc = tc
            yield cell


def convert_table_to_text(
    table: docx.table.Table | pptx.table.Table,
    fmt: str = "plain",
) -> str:
    """Convert a table to text using tabulate."""
    rows = list(table.rows)
    headers = [cell.text for cell in get_visual_cells(rows[0])]
    data = [[cell.text for cell in get_visual_cells(row)] for row in rows[1:]]
    return tabulate(data, headers=headers, tablefmt=fmt)
