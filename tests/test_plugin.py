from __future__ import annotations

import datetime
import os
import subprocess
from typing import Iterator
from typing import Mapping
from typing import Sequence
from typing import TYPE_CHECKING

import jinja2
import pytest
from lektor.environment import PRIMARY_ALT
from lektor.types import RawValue

from conftest import DummyGitRepo
from lektor_git_timestamp import _compute_checksum
from lektor_git_timestamp import _fs_mtime
from lektor_git_timestamp import _is_dirty
from lektor_git_timestamp import _iter_timestamps
from lektor_git_timestamp import ConfigurationError
from lektor_git_timestamp import get_mtime
from lektor_git_timestamp import GitTimestampDescriptor
from lektor_git_timestamp import GitTimestampPlugin
from lektor_git_timestamp import GitTimestampSource
from lektor_git_timestamp import GitTimestampType
from lektor_git_timestamp import run_git
from lektor_git_timestamp import Strategy
from lektor_git_timestamp import Timestamp

if TYPE_CHECKING:
    from lektor.context import Context
    from lektor.db import Pad
    from lektor.db import Record
    from lektor.environment import Environment


def test_run_git() -> None:
    output = run_git("--version")
    assert output.startswith("git version")


def test_run_git_output_stderr_on_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        run_git("unknown-command-xxx")
    out, err = capsys.readouterr()
    assert "unknown-command-xxx" in err


class Test__fs_mtime:
    def test(self, git_repo: DummyGitRepo) -> None:
        ts = 1589238180
        git_repo.touch("test.txt", ts)
        assert _fs_mtime(["test.txt"]) == ts

    def test_missing_file(self, git_repo: DummyGitRepo, env: Environment) -> None:
        assert _fs_mtime(["test.txt"]) is None


class Test__is_dirty:
    def test_dirty_if_not_in_git(self, git_repo: DummyGitRepo) -> None:
        git_repo.touch("test.txt")
        assert _is_dirty("test.txt")

    def test_clean(self, git_repo: DummyGitRepo) -> None:
        git_repo.commit("test.txt")
        assert not _is_dirty("test.txt")

    def test_dirty(self, git_repo: DummyGitRepo) -> None:
        git_repo.commit("test.txt")
        git_repo.modify("test.txt")
        assert _is_dirty("test.txt")


class Test__iter_timestamps:
    def test_from_git(self, git_repo: DummyGitRepo) -> None:
        plugin_config: dict[str, str] = {}
        ts = 1589238186
        git_repo.commit("test.txt", ts, "message")
        assert list(_iter_timestamps(["test.txt"], plugin_config)) == [
            (ts, "message\n")
        ]

    def test_from_mtime(self, git_repo: DummyGitRepo) -> None:
        plugin_config: dict[str, str] = {}
        ts = 1589238186
        git_repo.touch("test.txt", ts)
        assert list(_iter_timestamps(["test.txt"], plugin_config)) == [(ts, None)]

    def test_from_mtime_and_git(self, git_repo: DummyGitRepo) -> None:
        plugin_config: dict[str, str] = {}
        ts1 = 1589238000
        ts2 = 1589238180
        git_repo.commit("test.txt", ts1, "commit")
        git_repo.modify("test.txt")
        git_repo.touch("test.txt", ts2)
        assert list(_iter_timestamps(["test.txt"], plugin_config)) == [
            (ts2, None),
            (ts1, "commit\n"),
        ]

    @pytest.mark.parametrize(
        "plugin_config, expected_commits",
        [
            ({}, 1),
            ({"follow_renames": "yes"}, 3),
            ({"follow_renames": "yes", "follow_rename_threshold": "10"}, 3),
            ({"follow_renames": "yes", "follow_rename_threshold": "99.99"}, 2),
            ({"follow_renames": "no"}, 1),
        ],
    )
    def test_follow(
        self,
        git_repo: DummyGitRepo,
        plugin_config: Mapping[str, str],
        expected_commits: int,
    ) -> None:
        ts1 = 1589238000
        ts2 = 1589238180
        ts3 = 1589238360
        git_repo.commit("name1.txt", ts1, "commit 1", data="content\nline2\n")
        git_repo.commit("name2.txt", ts2, "commit 2", data="content\n")
        git_repo.commit("name3.txt", ts3, "commit 3", data="content\n")
        assert (
            list(_iter_timestamps(["name3.txt"], plugin_config))
            == [
                (ts3, "commit 3\n"),
                (ts2, "commit 2\n"),
                (ts1, "commit 1\n"),
            ][:expected_commits]
        )

    def test_from_git_two_files(self, git_repo: DummyGitRepo) -> None:
        plugin_config: dict[str, str] = {}
        ts1 = 1589238186
        ts2 = 1589238198
        git_repo.commit("test1.txt", ts1, "message1")
        git_repo.commit("test2.txt", ts2, "message2")
        assert list(_iter_timestamps(["test1.txt", "test2.txt"], plugin_config)) == [
            (ts2, "message2\n"),
            (ts1, "message1\n"),
        ]

    def test_raises_configuration_error(self, git_repo: DummyGitRepo) -> None:
        plugin_config = {"follow_renames": "true"}
        with pytest.raises(ConfigurationError):
            next(_iter_timestamps(["name1.txt", "name2.txt"], plugin_config))


class Test_get_mtime:
    def test_not_in_git(self) -> None:
        ts = 1589238006
        timestamps = (Timestamp(ts, None),)
        assert get_mtime(timestamps) == ts

    def test_clean(self, git_repo: DummyGitRepo) -> None:
        ts = 1589238186
        timestamps = (Timestamp(ts, "commit message"),)
        assert get_mtime(timestamps) == ts

    def test_dirty(self, git_repo: DummyGitRepo) -> None:
        ts = 1589238246
        timestamps = (
            Timestamp(ts, None),
            Timestamp(ts - 60, "commit message"),
            Timestamp(ts - 120, "first message"),
        )
        assert get_mtime(timestamps, ignore_commits=r"ignore") == ts

    def test_ignore_commits(self, git_repo: DummyGitRepo) -> None:
        ts1 = 1589238000
        ts2 = 1589238180
        timestamps = (
            Timestamp(ts2, "[skip] commit 2"),
            Timestamp(ts1, "commit 1"),
        )
        assert get_mtime(timestamps, ignore_commits=r"\[skip\]") == ts1

    def test_skip_first_commit(self, git_repo: DummyGitRepo) -> None:
        ts1 = 1589238000
        ts2 = 1589238180
        timestamps = (
            Timestamp(ts2, "commit 2"),
            Timestamp(ts1, "commit 1"),
        )
        assert get_mtime(timestamps[1:], skip_first_commit=True) is None
        assert get_mtime(timestamps, skip_first_commit=True) == ts2

    def test_first(self, git_repo: DummyGitRepo) -> None:
        ts1 = 1589238000
        ts2 = 1589238180
        timestamps = (
            Timestamp(ts2, "commit 2"),
            Timestamp(ts1, "commit 1"),
        )
        assert get_mtime(timestamps, strategy=Strategy.FIRST) == ts1

    def test_earliest(self, git_repo: DummyGitRepo) -> None:
        ts1 = 1589238000
        ts2 = 1589237700
        ts3 = 1589238180
        timestamps = (
            Timestamp(ts3, "commit 3"),
            Timestamp(ts2, "commit 2"),
            Timestamp(ts1, "commit 1"),
        )
        assert get_mtime(timestamps, strategy=Strategy.EARLIEST) == ts2

    def test_latest(self, git_repo: DummyGitRepo) -> None:
        ts1 = 1589238000
        ts2 = 1589238300
        ts3 = 1589238180
        timestamps = (
            Timestamp(ts3, "commit 3"),
            Timestamp(ts2, "commit 2"),
            Timestamp(ts1, "commit 1"),
        )
        assert get_mtime(timestamps, strategy=Strategy.LATEST) == ts2

    def test_missing_file(self, git_repo: DummyGitRepo) -> None:
        timestamps = ()
        assert get_mtime(timestamps) is None


class DummyPage:
    alt = PRIMARY_ALT

    def __init__(
        self, source_filenames: Sequence[str], path: str = "/", pad: Pad | None = None
    ):
        self.source_filenames = source_filenames
        self.path = path
        self.pad = pad

    @property
    def source_filename(self) -> str | None:
        return next(self.iter_source_filenames(), None)

    def iter_source_filenames(self) -> Iterator[str]:
        return iter(self.source_filenames)


class TestGitTimestampSource:
    @pytest.fixture
    def ts_now(self) -> int:
        return 1592256980

    @pytest.fixture
    def record(self, git_repo: DummyGitRepo, ts_now: int, pad: Pad) -> Record:
        git_repo.touch("test.txt", ts_now)
        source_filename = os.path.abspath("test.txt")
        return DummyPage([source_filename], path="/test", pad=pad)

    @pytest.fixture
    def src(self, record: Record) -> GitTimestampSource:
        return GitTimestampSource(record)

    def test_path(self, src: GitTimestampSource, record: Record) -> None:
        assert src.path == record.path + "@git-timestamp"

    def test_get_checksum(self, src: GitTimestampSource, record: Record) -> None:
        assert src.get_checksum("path_cache") == _compute_checksum(src.timestamps)

    def test_timestamps(self, src: GitTimestampSource, ts_now: int) -> None:
        assert src.timestamps == (Timestamp(ts_now, None),)


@pytest.mark.parametrize(
    ("data", "checksum"),
    [
        ((), "5d460934f4a194c28ce73ada3b56d2e025d5c47c"),
        (
            (Timestamp(1592256980, "message"),),
            "992a4429d547b2354f13523aecb3876eeef6de55",
        ),
    ],
)
def test__compute_checksum(data: tuple[Timestamp, ...], checksum: str) -> None:
    # These checksums should be portable across platforms
    assert _compute_checksum(data) == checksum


class TestGitTimestampDescriptor:
    @pytest.fixture
    def desc(self) -> GitTimestampDescriptor:
        raw = RawValue("test", None)
        return GitTimestampDescriptor(raw)

    @pytest.fixture
    def record(self, git_repo: DummyGitRepo, pad: Pad) -> Record:
        source_filename = os.path.abspath("test.txt")
        return DummyPage([source_filename], pad=pad)

    def test_class_descriptor(self, desc: GitTimestampDescriptor) -> None:
        assert desc.__get__(None) is desc

    def test_get(
        self, desc: GitTimestampDescriptor, git_repo: DummyGitRepo, record: Record
    ) -> None:
        dt = datetime.datetime.now().replace(microsecond=0)
        git_repo.commit("test.txt", dt)
        assert desc.__get__(record) == dt

    def test_get_returns_undefined(
        self, desc: GitTimestampDescriptor, record: Record
    ) -> None:
        assert jinja2.is_undefined(desc.__get__(record))

    def test_get_declares_dependency(
        self, desc: GitTimestampDescriptor, record: Record, ctx: Context
    ) -> None:
        desc.__get__(record)
        virtual_dependencies = ctx.referenced_virtual_dependencies
        if hasattr(virtual_dependencies, "values"):  # Lektor < 3.4.0b5
            virtual_dependencies = set(virtual_dependencies.values())
        assert "/@git-timestamp" in {v.path for v in virtual_dependencies}


class TestGitTimestampType:
    @pytest.fixture
    def type_(self, env: Environment) -> GitTimestampType:
        options: dict[str, str] = {}
        return GitTimestampType(env, options)

    def test_value_from_raw_explicit(self, type_: GitTimestampType) -> None:
        raw = RawValue("test", "2020-01-02 03:04")
        assert type_.value_from_raw(raw) == datetime.datetime(2020, 1, 2, 3, 4)

    def test_value_from_raw(self, type_: GitTimestampType) -> None:
        raw = RawValue("test", None)
        value = type_.value_from_raw(raw)
        assert isinstance(value, GitTimestampDescriptor)


class TestGitTimestampPlugin:
    @pytest.fixture
    def plugin(self, env: Environment) -> GitTimestampPlugin:
        return GitTimestampPlugin(env, "git-timestamp")

    @pytest.fixture
    def record(self, git_repo: DummyGitRepo, pad: Pad) -> Record:
        source_filename = os.path.abspath("test.txt")
        return DummyPage([source_filename], pad=pad)

    def test_on_setup_env(self, plugin: GitTimestampPlugin, env: Environment) -> None:
        plugin.on_setup_env()
        assert env.types["gittimestamp"] is GitTimestampType

    def test_resolve_virtual_path(
        self, plugin: GitTimestampPlugin, record: Record
    ) -> None:
        pieces: list[str] = []
        src = plugin.resolve_virtual_path(record, pieces)
        assert isinstance(src, GitTimestampSource)
        assert src.record is record

    def test_resolve_virtual_path_returns_none(
        self, plugin: GitTimestampPlugin, record: Record
    ) -> None:
        pieces = ["x"]
        assert plugin.resolve_virtual_path(record, pieces) is None
