# -*- coding: utf-8 -*-
from collections import namedtuple
import datetime
import os
import re
import subprocess

import jinja2
from lektor.pluginsystem import Plugin
from lektor.reporter import reporter
from lektor.types import DateTimeType


def run_git(*args):
    cmd = ['git'] + list(args)
    output = subprocess.check_output(cmd, universal_newlines=True)
    return output.rstrip()


def _fs_mtime(filename):
    try:
        st = os.stat(filename)
    except OSError as exc:
        reporter.report_generic("{}: {!s}".format(filename, exc))
        return None
    else:
        # (truncate to one second resolution)
        return int(st.st_mtime)


def _is_dirty(filename):
    status = run_git('status', '-z', '--', filename)
    return status != ''


timestamp = namedtuple('timestamp', ['ts', 'commit_message'])


def _iter_timestamps(filename):
    output = run_git('log', '--pretty=format:%at %B', '-z',
                     '--follow', '--remove-empty',
                     '--', filename)
    if not output or _is_dirty(filename):
        ts = _fs_mtime(filename)
        if ts is not None:
            yield timestamp(ts, None)
    if output:
        for line in output.split('\0'):
            ts, _, commit_message = line.partition(' ')
            yield timestamp(int(ts), commit_message)


def get_mtime(filename, ignore_commits=None):
    def is_ignored(timestamp):
        if ignore_commits is None:
            return False
        message = timestamp.commit_message
        if message is None:
            return False
        return re.search(ignore_commits, message) is not None

    for timestamp in _iter_timestamps(filename):
        if not is_ignored(timestamp):
            return timestamp.ts


class GitTimestampDescriptor(object):
    def __init__(self, ignore_commits=None):
        self.ignore_commits = ignore_commits

    def _get_mtime(self, filename):
        return get_mtime(filename, ignore_commits=self.ignore_commits)

    def __get__(self, obj, type_=None):
        if obj is None:
            return self
        mtime = max(map(self._get_mtime, obj.iter_source_filenames()))
        return datetime.datetime.fromtimestamp(mtime)


class GitTimestampType(DateTimeType):
    def value_from_raw(self, raw):
        value = super(GitTimestampType, self).value_from_raw(raw)
        if jinja2.is_undefined(value):
            value = GitTimestampDescriptor(
                ignore_commits=self.options.get('ignore_commits'))
        return value


class GitTimestampPlugin(Plugin):
    name = 'git-timestamp'
    description = u'Lektor type to deduce page modification time from git'

    def on_setup_env(self, **extra):
        self.env.add_type(GitTimestampType)
