# -*- coding: utf-8 -*-
import datetime
import os
import subprocess

import pytest

from lektor.context import Context
from lektor.db import Page
from lektor.project import Project


@pytest.fixture(scope='session')
def project(tmp_path_factory):
    site_path = tmp_path_factory.mktemp('site')
    project_file = site_path / 'site.lektorproject'
    project_file.write_text(u"""
    [project]
    name = Test Project
    """)
    return Project.from_file(str(project_file))


@pytest.fixture
def env(project):
    return project.make_env(load_plugins=False)


@pytest.fixture
def pad(env):
    return env.new_pad()


@pytest.fixture
def page(pad, model_data):
    return Page(pad, model_data)


@pytest.fixture
def ctx(pad):
    with Context(pad=pad) as ctx:
        yield ctx


try:
    utc = datetime.timezone.utc
except AttributeError:          # py2
    class UTC(datetime.tzinfo):
        def utcoffset(self, dt):
            return datetime.timedelta(0)

        def tzname(self, dt):
            return "UTC"

        def dst(self, dt):
            return datetime.timedelta(0)
    utc = UTC()


class DummyGitRepo(object):
    def __init__(self, work_tree):
        self.work_tree = work_tree
        self.run_git('init')
        self.run_git('commit', '--message=initial', '--allow-empty')

    def run_git(self, *args, **kwargs):
        cmd = ['git'] + list(args)
        subprocess.check_call(cmd, cwd=str(self.work_tree), **kwargs)

    def touch(self, filename, ts=None):
        file_path = self.work_tree / filename
        file_path.touch()
        if ts is not None:
            if isinstance(ts, datetime.datetime):
                ts = int(ts.strftime("%s"))
            os.utime(str(file_path), (ts, ts))

    def modify(self, filename, ts=None):
        file_path = self.work_tree / filename
        with file_path.open('at') as f:
            f.write(u'---\nchanged\n')
        if ts is not None:
            self.touch(filename, ts)

    def commit(self, filename, ts=None, message='test'):
        if ts is None:
            env = os.environ
        else:
            if isinstance(ts, datetime.datetime):
                ts = int(ts.strftime("%s"))
            dt = datetime.datetime.fromtimestamp(ts, utc)
            env = os.environ.copy()
            env['GIT_AUTHOR_DATE'] = dt.isoformat('T')
        self.modify(filename)
        self.run_git('add', str(filename))
        self.run_git('commit', '--message', str(message), env=env)


@pytest.fixture
def git_repo(tmp_path):
    os.chdir(str(tmp_path))
    return DummyGitRepo(tmp_path)
