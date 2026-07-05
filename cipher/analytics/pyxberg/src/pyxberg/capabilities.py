# Filetype names (matching filetyper's registry `name` field) this package
# extracts confidently. Which analytic supports which filetype is this
# analytic's own concern, not a shared registry flag.
#
# Deliberately conservative: kreuzberg supports more formats than this in
# principle (its Metadata TypedDicts hint at bibtex/citation/fictionbook/dbf/
# jats/pst support too), but this starts with the well-established office/
# document formats and should grow as the exotic ones (hwp, one, postscript,
# visio, ai) get verified against real samples.
SUPPORTED_FILETYPES = frozenset({
    "pdf",
    "doc",
    "docx",
    "dotx",
    "xls",
    "xlsb",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    "epub",
})
