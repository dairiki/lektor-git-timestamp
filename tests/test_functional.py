from __future__ import annotations

import datetime
import shutil
from importlib import metadata
from pathlib import Path
from typing import Iterable
from typing import TYPE_CHECKING

import jinja2
import lektor.metaformat
import pytest
from lektor.project import Project
from packaging.version import Version

from conftest import DummyGitRepo

if TYPE_CHECKING:
    from _typeshed import StrPath
    from lektor.db import Pad
    from lektor.environment import Environment


@pytest.fixture(params=(False, True))
def enable_alts(request: pytest.FixtureRequest) -> bool:
    return request.param  # type: ignore[no-any-return]


ALT_CONFIG = """
[alternatives.en]
name = English
primary = yes

[alternatives.de]
name = German
url_prefix = /de/
locale = de
"""


@pytest.fixture
def project(tmp_path: Path, enable_alts: bool) -> Project:
    site_src = Path(__file__).parent / "test-site"
    site_path = tmp_path / "site"
    shutil.copytree(site_src, site_path)
    if enable_alts:
        with Path(site_path, "Test Site.lektorproject").open("a") as fp:
            fp.write(ALT_CONFIG)
    return Project.from_path(site_path)


@pytest.fixture
def env(project: Project) -> Environment:
    return project.make_env(load_plugins=True)


@pytest.fixture(scope="session")
def now() -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0)


@pytest.fixture
def pub_date(now: datetime.datetime) -> datetime.datetime:
    return now - datetime.timedelta(hours=3)


@pytest.fixture
def last_mod(now: datetime.datetime) -> datetime.datetime:
    return now - datetime.timedelta(hours=1)


def write_data(filename: StrPath, data: Iterable[tuple[str, str]]) -> None:
    """Write lektor .lr serialized data."""
    with open(filename, "wb") as f:
        for chunk in lektor.metaformat.serialize(data, encoding="utf-8"):
            f.write(chunk)


def test_pub_date_for_untracked_file(
    git_repo: DummyGitRepo, pad: Pad, pub_date: datetime.datetime
) -> None:
    git_repo.touch("site/content/contents.lr", pub_date)
    assert pad.root["pub_date"] == pub_date
    assert jinja2.is_undefined(pad.root["last_mod"])


def test_explicit_pub_date(
    git_repo: DummyGitRepo,
    pad: Pad,
    pub_date: datetime.datetime,
    now: datetime.datetime,
) -> None:
    write_data(
        "site/content/contents.lr",
        [
            ("pub_date", pub_date.isoformat(" ")),
        ],
    )
    git_repo.commit("site/content/contents.lr", now)
    assert pad.root["pub_date"] == pub_date


def test_last_mod_ignores_initial_commit(
    git_repo: DummyGitRepo, pad: Pad, pub_date: datetime.datetime
) -> None:
    git_repo.commit("site/content/contents.lr", pub_date)
    assert pad.root["pub_date"] == pub_date
    assert jinja2.is_undefined(pad.root["last_mod"])


def test_last_mod(
    git_repo: DummyGitRepo,
    pad: Pad,
    pub_date: datetime.datetime,
    last_mod: datetime.datetime,
) -> None:
    git_repo.commit("site/content/contents.lr", pub_date)
    first_mod = last_mod - datetime.timedelta(minutes=30)
    git_repo.commit("site/content/contents.lr", first_mod)
    git_repo.commit("site/content/contents.lr", last_mod)
    assert pad.root["pub_date"] == pub_date
    assert pad.root["last_mod"] == last_mod


def test_pub_date_ignores_nochange(
    git_repo: DummyGitRepo,
    pad: Pad,
    pub_date: datetime.datetime,
    now: datetime.datetime,
) -> None:
    ignored_date = pub_date - datetime.timedelta(minutes=5)
    git_repo.commit(
        "site/content/contents.lr",
        ignored_date,
        message="Ignore this commit [nochange]",
    )
    git_repo.commit("site/content/contents.lr", pub_date)
    git_repo.commit(
        "site/content/contents.lr", now, message="Also ignore this commit [nochange]"
    )
    assert pad.root["pub_date"] == pub_date
    assert jinja2.is_undefined(pad.root["last_mod"])


def test_last_mod_ignores_nochange(
    git_repo: DummyGitRepo,
    pad: Pad,
    pub_date: datetime.datetime,
    last_mod: datetime.datetime,
    now: datetime.datetime,
) -> None:
    git_repo.commit("site/content/contents.lr", pub_date)
    git_repo.commit("site/content/contents.lr", last_mod)
    git_repo.commit("site/content/contents.lr", now, message="test [nochange]")
    assert pad.root["pub_date"] == pub_date
    assert pad.root["last_mod"] == last_mod


def test_last_mod_for_dirty_file(
    git_repo: DummyGitRepo,
    pad: Pad,
    pub_date: datetime.datetime,
    last_mod: datetime.datetime,
    now: datetime.datetime,
) -> None:
    git_repo.commit("site/content/contents.lr", pub_date)
    git_repo.commit("site/content/contents.lr", last_mod)
    git_repo.modify("site/content/contents.lr", now)
    assert pad.root["pub_date"] == pub_date
    assert pad.root["last_mod"] == now


def test_pub_date_de_file(
    git_repo: DummyGitRepo,
    pad: Pad,
    pub_date: datetime.datetime,
    now: datetime.datetime,
) -> None:
    git_repo.commit(
        ("site/content/contents+de.lr", "site/content/contents.lr"), pub_date
    )
    git_repo.touch("site/content/contents.lr", now)
    assert pad.root["pub_date"] == pub_date
    assert jinja2.is_undefined(pad.root["last_mod"])


def test_lastmod_de_file(
    git_repo: DummyGitRepo,
    pad: Pad,
    pub_date: datetime.datetime,
    now: datetime.datetime,
) -> None:
    git_repo.commit(
        ("site/content/contents+de.lr", "site/content/contents.lr"), pub_date
    )
    git_repo.modify("site/content/contents.lr", now)
    assert pad.root["pub_date"] == pub_date
    assert pad.root["last_mod"] == now


@pytest.mark.xfail(
    Version(metadata.version("lektor")) < Version("3.3"),
    reason="Lektor is too old to support sorting by descriptor-valued fields",
)
def test_get_sort_key(
    git_repo: DummyGitRepo, pad: Pad, pub_date: datetime.datetime
) -> None:
    git_repo.commit("site/content/contents.lr", pub_date)
    sort_key = pad.root.get_sort_key(["-pub_date"])
    assert [_.value for _ in sort_key] == [pub_date]
    assert sort_key[0].reverse
