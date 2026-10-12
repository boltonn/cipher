"""Member names -> safe, unique display paths.

Names are never used to write anything (bytes go to the output store by hash); they become the
`path` a file row shows. So this only has to make them clean and unique: forward slashes, no
drive letters, no `.`/`..`/empty parts, no control characters, and a `~2` suffix for a name an
archive lists twice (zip allows it).
"""

import re
from pathlib import PurePosixPath

_DRIVE = re.compile(r"^[A-Za-z]:")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def normalize_member_name(name: str) -> str:
    """A member name as a clean relative POSIX path ('' when nothing usable is left)."""
    name = _CONTROL.sub("", _DRIVE.sub("", name.replace("\\", "/")))
    parts = [part.strip() for part in name.split("/")]
    return "/".join(part for part in parts if part not in ("", ".", ".."))


class MemberNames:
    """Hands out unique display paths for one archive, deterministically (a re-run gets the same ones)."""

    def __init__(self) -> None:
        self._taken: set[str] = set()
        self._unnamed = 0

    def claim(self, name: str) -> str:
        """The unique display path for the next member called `name`."""
        path = normalize_member_name(name)
        if not path:
            self._unnamed += 1
            path = f"_unnamed_{self._unnamed}"
        candidate, n = path, 1
        while candidate in self._taken:
            n += 1
            pure = PurePosixPath(path)
            candidate = str(pure.with_name(f"{pure.stem}~{n}{pure.suffix}"))
        self._taken.add(candidate)
        return candidate
