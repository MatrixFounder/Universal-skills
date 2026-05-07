"""XML namespaces, OOXML rel-types, content-types, and editor-wide constants used by the xlsx_comment package.

Migrated from `xlsx_add_comment.py` F-Constants region (lines 140-178)
during Task 002 (module split). Verbatim move — no value changes. The
constants are consumed by every other module in the package; this is
the canonical source of truth.
"""
__all__ = [
    "SS_NS", "R_NS", "PR_NS", "CT_NS", "V_NS", "O_NS", "X_NS",
    "THREADED_NS",
    "COMMENTS_REL_TYPE", "COMMENTS_CT",
    "VML_REL_TYPE", "VML_CT",
    "THREADED_REL_TYPE", "THREADED_CT",
    "PERSON_REL_TYPE", "PERSON_CT",
    "DEFAULT_VML_ANCHOR",
    "BATCH_MAX_BYTES",
]

SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"
X_NS = "urn:schemas-microsoft-com:office:excel"
THREADED_NS = "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"

COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CT = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml"
)
VML_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing"
)
VML_CT = "application/vnd.openxmlformats-officedocument.vmlDrawing"
THREADED_REL_TYPE = (
    "http://schemas.microsoft.com/office/2017/10/relationships/threadedComment"
)
THREADED_CT = (
    "application/vnd.ms-excel.threadedcomments+xml"
)
PERSON_REL_TYPE = (
    "http://schemas.microsoft.com/office/2017/10/relationships/person"
)
PERSON_CT = "application/vnd.ms-excel.person+xml"

# Default Excel-style VML anchor (R9.c — locked, no custom offsets in v1).
# Order: from-col, from-col-off, from-row, from-row-off, to-col, to-col-off,
# to-row, to-row-off (1024-twip units, per Excel convention).
DEFAULT_VML_ANCHOR = "3, 15, 0, 5, 5, 31, 4, 8"

# 8 MiB pre-parse cap on --batch input (TASK m2 / m-4 boundary).
BATCH_MAX_BYTES = 8 * 1024 * 1024
