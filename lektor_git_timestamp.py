from __future__ import annotations

import datetime
import enum
import hashlib
import os
import pickle
import re
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from typing import Iterable
from typing import Iterator
from typing import Mapping
from typing import NamedTuple
from typing import overload
from typing import Sequence
from typing import TYPE_CHECKING

import jinja2
from lektor.context import get_ctx
from lektor.pluginsystem import get_plugin
from lektor.pluginsystem import Plugin
from lektor.sourceobj import VirtualSourceObject
from lektor.types import DateTimeType
from lektor.utils import bool_from_string
from lektorlib.recordcache import get_or_create_virtual
from werkzeug.utils import cached_property

if TYPE_CHECKING:
    from _typeshed import StrPath
    from lektor.builder import PathCache
    from lektor.db import Record
    from lektor.types.base import RawValue


VIRTUAL_PATH_PREFIX = "git-timestamp"


class ConfigurationError(ValueError):
    """Invalid configuration setting."""


def run_git(*args: str | StrPath) -> str:
    cmd = ("git", *args)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        if exc.stderr is not None:
            sys.stderr.write(exc.stderr)
        raise
    return proc.stdout


def _fs_mtime(filenames: Iterable[StrPath]) -> int | None:
    mtimes = []
    for filename in filenames:
        with suppress(OSError):
            mtimes.append(os.stat(filename).st_mtime)
    if len(mtimes) == 0:
        return None
    # (truncate to one second resolution)
    return int(max(mtimes))


def _is_dirty(filename: StrPath) -> bool:
    status = run_git("status", "-z", "--", filename)
    return status != ""


class Timestamp(NamedTuple):
    ts: int
    commit_message: str | None


_FOLLOW_RENAMES_NOT_ALLOWED = (
    "The follow_renames option is not supported when records have"
    " multiple source files (e.g. when alts are in use)."
)


def _iter_timestamps(
    filenames: Sequence[StrPath], config: Mapping[str, str]
) -> Iterator[Timestamp]:
    options = ["--remove-empty"]
    follow_renames = bool_from_string(config.get("follow_renames", "false"))
    if follow_renames:
        if len(filenames) > 1:
            raise ConfigurationError(_FOLLOW_RENAMES_NOT_ALLOWED)
        options.append("--follow")
        with suppress(LookupError, ValueError):
            threshold = float(config["follow_rename_threshold"])
            if 0 < threshold < 100:
                options.append(f"-M{threshold:.4f}%")

    output = run_git(
        "log",
        "--pretty=format:%at %B",
        "-z",
        *options,
        "--",
        *filenames,
    )

    if not output:
        ts = _fs_mtime(filenames)
    else:
        ts = _fs_mtime(filter(_is_dirty, filenames))
    if ts is not None:
        yield Timestamp(ts, None)

    if output:
        for line in output.split("\0"):
            tstamp, _, commit_message = line.partition(" ")
            yield Timestamp(int(tstamp), commit_message)


class Strategy(enum.Enum):
    FIRST = "first"
    EARLIEST = "earliest"
    LATEST = "latest"
    LAST = "last"


def get_mtime(
    timestamps: Iterable[Timestamp],
    ignore_commits: str | re.Pattern[str] | None = None,
    strategy: Strategy = Strategy.LAST,
    skip_first_commit: bool = False,
) -> int | None:
    def is_not_ignored(timestamp: Timestamp) -> bool:
        if ignore_commits is None:
            return True
        message = timestamp.commit_message
        if message is None:
            return True
        return re.search(ignore_commits, message) is None

    filtered = list(filter(is_not_ignored, timestamps))
    if skip_first_commit:
        filtered = filtered[:-1]

    if len(filtered) == 0:
        return None
    if strategy is Strategy.FIRST:
        return filtered[-1].ts
    if strategy is Strategy.EARLIEST:
        return min(timestamp.ts for timestamp in filtered)
    if strategy is Strategy.LATEST:
        return max(timestamp.ts for timestamp in filtered)
    assert strategy is Strategy.LAST
    return filtered[0].ts


def _compute_checksum(data: tuple[Timestamp, ...]) -> str:
    return hashlib.sha1(pickle.dumps(data, protocol=0)).hexdigest()


class GitTimestampSource(VirtualSourceObject):  # type: ignore[misc]
    @classmethod
    def get(cls, record: Record) -> GitTimestampSource:
        def creator() -> GitTimestampSource:
            return cls(record)

        return get_or_create_virtual(record, VIRTUAL_PATH_PREFIX, creator)

    @property
    def path(self) -> str:
        return f"{self.record.path}@{VIRTUAL_PATH_PREFIX}"

    def get_checksum(self, path_cache: PathCache) -> str:
        return _compute_checksum(self.timestamps)

    @cached_property
    def timestamps(self) -> tuple[Timestamp, ...]:
        plugin_config: Mapping[str, str] = {}
        with suppress(LookupError):
            plugin_config = get_plugin(GitTimestampPlugin, self.pad.env).get_config()
        source_filenames = tuple(self.iter_source_filenames())
        return tuple(_iter_timestamps(source_filenames, plugin_config))

    def iter_source_filenames(self) -> Iterator[StrPath]:
        # Compatibility: The default implementation of
        # VirtualSourceObject.iter_source_filenames in Lektor < 3.4
        # returns only the primary source filename.
        return self.record.iter_source_filenames()  # type: ignore[no-any-return]


@dataclass
class GitTimestampDescriptor:
    raw: RawValue
    ignore_commits: str | re.Pattern[str] | None = None
    strategy: Strategy = Strategy.LAST
    skip_first_commit: bool = False

    @overload
    def __get__(self, obj: None) -> GitTimestampDescriptor:
        ...

    @overload
    def __get__(self, obj: Record) -> datetime.datetime | jinja2.Undefined:
        ...

    def __get__(
        self, obj: Record | None, type_: object = None
    ) -> GitTimestampDescriptor | datetime.datetime | jinja2.Undefined:
        if obj is None:
            return self
        ctx = get_ctx()
        src = GitTimestampSource.get(obj)
        if ctx:
            ctx.record_virtual_dependency(src)
        mtime = get_mtime(
            src.timestamps,
            ignore_commits=self.ignore_commits,
            strategy=self.strategy,
            skip_first_commit=self.skip_first_commit,
        )
        if mtime is None:
            return self.raw.missing_value(  # type: ignore[no-any-return]
                "no suitable git timestamp exists"
            )
        return datetime.datetime.fromtimestamp(mtime)


class GitTimestampType(DateTimeType):  # type: ignore[misc]
    def value_from_raw(
        self, raw: RawValue
    ) -> GitTimestampDescriptor | datetime.datetime:
        value = super().value_from_raw(raw)
        if not jinja2.is_undefined(value):
            assert isinstance(value, datetime.datetime)
            return value

        options = self.options
        try:
            strategy = Strategy(options["strategy"])
        except (KeyError, ValueError):
            strategy = Strategy.LAST
        return GitTimestampDescriptor(
            raw,
            ignore_commits=options.get("ignore_commits"),
            strategy=strategy,
            skip_first_commit=bool_from_string(options.get("skip_first_commit", False)),
        )


class GitTimestampPlugin(Plugin):  # type: ignore[misc]
    name = "git-timestamp"
    description = "Lektor type to deduce page modification time from git"

    def on_setup_env(self, **extra: Any) -> None:
        env = self.env
        env.add_type(GitTimestampType)
        env.virtualpathresolver(VIRTUAL_PATH_PREFIX)(self.resolve_virtual_path)

    @staticmethod
    def resolve_virtual_path(
        record: Record, pieces: Sequence[str]
    ) -> GitTimestampSource | None:
        if len(pieces) == 0:
            return GitTimestampSource.get(record)
        return None
