from __future__ import annotations

import datetime
import enum
import hashlib
import os
import pickle
import re
import subprocess
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
from lektor.reporter import reporter
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


def run_git(*args: str | StrPath) -> str:
    cmd = ("git", *args)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


def _fs_mtime(filename: StrPath) -> int | None:
    try:
        st = os.stat(filename)
    except OSError as exc:
        reporter.report_generic(f"{filename}: {exc!s}")
        return None
    else:
        # (truncate to one second resolution)
        return int(st.st_mtime)


def _is_dirty(filename: StrPath) -> bool:
    status = run_git("status", "-z", "--", filename)
    return status != ""


class Timestamp(NamedTuple):
    ts: int
    commit_message: str | None


def _iter_timestamps(
    filename: StrPath, config: Mapping[str, str]
) -> Iterator[Timestamp]:
    options = ["--remove-empty"]
    follow_renames = bool_from_string(config.get("follow_renames", "true"))
    if follow_renames:
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
        filename,
    )
    if not output or _is_dirty(filename):
        ts = _fs_mtime(filename)
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

        return tuple(_iter_timestamps(self.source_filename, plugin_config))


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
