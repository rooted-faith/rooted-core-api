from enum import StrEnum

# On each bible.verses.lines entry: does it continue the previous line's publisher block? Absent on lines filled before ROO-67.
CONTINUES_KEY = "continues"


class BibleErrorCode(StrEnum):
    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
    PASSAGE_NOT_FOUND = "PASSAGE_NOT_FOUND"
