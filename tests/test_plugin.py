# -*- coding: utf-8 -*-
import datetime
import os
import re
import subprocess

import pytest

import jinja2
from lektor.reporter import BufferReporter
from lektor.types import RawValue

from lektor_git_timestamp import (
    run_git,
    _fs_mtime,
    _is_dirty,
    _iter_timestamps,
    get_mtime,
    GitTimestampDescriptor,
    GitTimestampType,
    GitTimestampPlugin,
    )


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


def test_run_git():
    output = run_git('--version')
    assert output.startswith('git version')


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
            os.utime(str(file_path), (ts, ts))

    def modify(self, filename):
        file_path = self.work_tree / filename
        with file_path.open('at') as f:
            f.write(u'changed\n')

    def commit(self, filename, ts=None, message='test'):
        if ts is None:
            env = os.environ
        else:
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


class Test__fs_mtime(object):
    def test(self, git_repo):
        ts = 1589238180
        git_repo.touch('test.txt', ts)
        assert _fs_mtime('test.txt') == ts

    def test_missing_file(self, git_repo, env):
        with BufferReporter(env) as reporter:
            assert _fs_mtime('test.txt') is None
        event, data = reporter.buffer[0]
        assert event == 'generic'
        assert re.match(r'(?i)test.txt: .*\bno such file', data['message'])


class Test__is_dirty(object):
    def test_dirty_if_not_in_git(self, git_repo):
        git_repo.touch('test.txt')
        assert _is_dirty('test.txt')

    def test_clean(self, git_repo):
        git_repo.commit('test.txt')
        assert not _is_dirty('test.txt')

    def test_dirty(self, git_repo):
        git_repo.commit('test.txt')
        git_repo.modify('test.txt')
        assert _is_dirty('test.txt')


class Test__iter_timestamps(object):
    def test_from_git(self, git_repo):
        ts = 1589238186
        git_repo.commit('test.txt', ts, 'message')
        assert list(_iter_timestamps('test.txt')) == [(ts, 'message')]

    def test_from_mtime(self, git_repo):
        ts = 1589238186
        git_repo.touch('test.txt', ts)
        assert list(_iter_timestamps('test.txt')) == [(ts, None)]

    def test_from_mtime_and_git(self, git_repo):
        ts1 = 1589238000
        ts2 = 1589238180
        git_repo.commit('test.txt', ts1, 'commit')
        git_repo.modify('test.txt')
        git_repo.touch('test.txt', ts2)
        assert list(_iter_timestamps('test.txt')) == [
            (ts2, None),
            (ts1, 'commit'),
            ]


class Test_get_mtime(object):
    def test_not_in_git(self, git_repo):
        ts = 1589238006
        git_repo.touch('test.txt', ts)
        assert get_mtime('test.txt') == ts

    def test_clean(self, git_repo):
        ts = 1589238186
        git_repo.commit('test.txt', ts)
        assert get_mtime('test.txt') == ts

    def test_dirty(self, git_repo):
        ts = 1589238246
        git_repo.commit('test.txt')
        git_repo.modify('test.txt')
        git_repo.touch('test.txt', ts)
        assert get_mtime('test.txt', ignore_commits=r'ignore') == ts

    def test_ignore_commits(self, git_repo):
        ts1 = 1589238000
        ts2 = 1589238180
        git_repo.commit('test.txt', ts1, 'commit 1')
        git_repo.commit('test.txt', ts2, '[skip] commit 2')
        assert get_mtime('test.txt', ignore_commits=r'\[skip\]') == ts1

    def test_skip_first_commit(self, git_repo):
        ts1 = 1589238000
        ts2 = 1589238180
        git_repo.commit('test.txt', ts1)
        assert get_mtime('test.txt', skip_first_commit=True) is None
        git_repo.commit('test.txt', ts2)
        assert get_mtime('test.txt', skip_first_commit=True) == ts2

    def test_first(self, git_repo):
        ts1 = 1589238000
        ts2 = 1589238180
        git_repo.commit('test.txt', ts1)
        git_repo.commit('test.txt', ts2)
        assert get_mtime('test.txt', strategy='first') == ts1

    def test_earliest(self, git_repo):
        ts1 = 1589238000
        ts2 = 1589237700
        ts3 = 1589238180
        git_repo.commit('test.txt', ts1)
        git_repo.commit('test.txt', ts2)
        git_repo.commit('test.txt', ts3)
        assert get_mtime('test.txt', strategy='earliest') == ts2

    def test_latest(self, git_repo):
        ts1 = 1589238000
        ts2 = 1589238300
        ts3 = 1589238180
        git_repo.commit('test.txt', ts1)
        git_repo.commit('test.txt', ts2)
        git_repo.commit('test.txt', ts3)
        assert get_mtime('test.txt', strategy='latest') == ts2

    def test_missing_file(self, git_repo):
        assert get_mtime('test.txt') is None


class DummyPage(object):
    def __init__(self, source_filename):
        self.source_filename = source_filename

    def iter_source_filenames(self):
        yield self.source_filename


class TestGitTimestampDescriptor(object):
    @pytest.fixture
    def desc(self):
        raw = RawValue('test', None)
        return GitTimestampDescriptor(raw)

    def test_class_descriptor(self, desc):
        assert desc.__get__(None, object) is desc

    def test_get(self, desc, git_repo):
        dt = datetime.datetime.now().replace(microsecond=0)
        ts = int(dt.strftime('%s'))
        git_repo.commit('test.txt', ts)
        record = DummyPage(source_filename=os.path.abspath('test.txt'))
        assert desc.__get__(record) == dt

    def test_get_returns_undefined(self, desc, git_repo):
        record = DummyPage(source_filename=os.path.abspath('test.txt'))
        assert jinja2.is_undefined(desc.__get__(record))


class TestGitTimestampType(object):
    @pytest.fixture
    def type_(self, env):
        options = {}
        return GitTimestampType(env, options)

    def test_value_from_raw_explicit(self, type_):
        raw = RawValue('test', '2020-01-02 03:04')
        assert type_.value_from_raw(raw) == datetime.datetime(2020, 1, 2, 3, 4)

    def test_value_from_raw(self, type_):
        raw = RawValue('test', None)
        value = type_.value_from_raw(raw)
        assert isinstance(value, GitTimestampDescriptor)


class TestGitTimestampPlugin(object):
    @pytest.fixture
    def plugin(self, env):
        return GitTimestampPlugin(env, 'git-timestamp')

    def test_on_setup_env(self, plugin, env):
        plugin.on_setup_env()
        assert env.types['gittimestamp'] is GitTimestampType
