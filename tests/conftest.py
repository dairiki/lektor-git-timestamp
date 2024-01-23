from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import MutableMapping
from typing import TYPE_CHECKING

import pytest
from lektor.context import Context
from lektor.db import Page
from lektor.project import Project

if TYPE_CHECKING:
    from _typeshed import StrPath
    from lektor.db import Pad
    from lektor.environment import Environment


@pytest.fixture
def site_path(tmp_path: Path) -> Path:
    path = tmp_path / "site"
    path.mkdir()
    return path


@pytest.fixture
def project(site_path: Path) -> Project:
    project_file = site_path / "site.lektorproject"
    project_file.write_text(
        """
    [project]
    name = Test Project
    """
    )
    return Project.from_file(project_file)


@pytest.fixture
def env(project: Project) -> Environment:
    return project.make_env(load_plugins=False)


@pytest.fixture
def pad(env: Environment) -> Pad:
    return env.new_pad()


@pytest.fixture
def page(pad: Pad, model_data: Mapping[str, Any]) -> Page:
    return Page(pad, model_data)


@pytest.fixture
def ctx(pad: Pad) -> Context:
    with Context(pad=pad) as ctx:
        yield ctx


utc = datetime.timezone.utc


class DummyGitRepo:
    def __init__(self, work_tree: Path):
        self.work_tree = work_tree
        self.run_git("init")
        self.run_git("commit", "--message=initial", "--allow-empty")

    def run_git(self, *args: str, **kwargs: Any) -> None:
        cmd = ["git"] + list(args)
        subprocess.check_call(cmd, cwd=self.work_tree, **kwargs)

    def touch(
        self, filename: StrPath, ts: int | datetime.datetime | None = None
    ) -> None:
        file_path = self.work_tree / filename
        file_path.touch()
        if ts is not None:
            if isinstance(ts, datetime.datetime):
                ts = int(ts.strftime("%s"))
            os.utime(file_path, (ts, ts))

    def modify(
        self, filename: StrPath, ts: int | datetime.datetime | None = None
    ) -> None:
        file_path = self.work_tree / filename
        with file_path.open("at") as f:
            f.write("---\nchanged\n")
        if ts is not None:
            self.touch(filename, ts)

    def commit(
        self,
        filename_: StrPath | tuple[StrPath, ...],
        ts: int | datetime.datetime | None = None,
        message: str = "test",
        data: str | None = None,
    ) -> None:
        env: MutableMapping[str, str]
        if ts is None:
            env = os.environ
        else:
            if isinstance(ts, datetime.datetime):
                ts = int(ts.strftime("%s"))
            dt = datetime.datetime.fromtimestamp(ts, utc)
            env = os.environ.copy()
            env["GIT_AUTHOR_DATE"] = dt.isoformat("T")

        filenames = filename_ if isinstance(filename_, tuple) else (filename_,)
        for filename in filenames:
            if data is not None:
                file_path = self.work_tree / filename
                file_path.write_text(data)
            else:
                self.modify(filename)

            self.run_git("add", os.fspath(filename))

        self.run_git("commit", "--message", str(message), env=env)


@pytest.fixture
def git_repo(tmp_path: Path) -> DummyGitRepo:
    os.chdir(tmp_path)
    return DummyGitRepo(tmp_path)
