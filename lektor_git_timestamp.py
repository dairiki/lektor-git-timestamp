# -*- coding: utf-8 -*-
import datetime
from itertools import count
import os
import re
import subprocess

import jinja2
from lektor.pluginsystem import Plugin
from lektor.types import DateTimeType


def run_git(*args):
    cmd = ['git'] + list(args)
    output = subprocess.check_output(cmd, universal_newlines=True)
    return output.rstrip()


def _fs_mtime(filename):
    st = os.stat(filename)
    # (truncate to one second resolution)
    return int(st.st_mtime)


def _git_mtime(filename, ignore_commits=None):
    # Since ignored commits are expected to not be very common,
    # checking back just one commit at a time is likely to be
    # significantly faster than fetching the entire log of all commits
    # for the file of interest, then filtering.

    # This iterative searching of commits could be avoided by using
    # `git log --invert-grep --grep=<ignore>`, however this requires
    # git >= 2.4.0 (which is not easily available on my old Debian
    # Jessie machine)

    def is_ignored(log_message):
        if ignore_commits is None:
            return False
        return re.search(ignore_commits, log_message) is not None

    for skip in count(0):
        output = run_git('log', '--pretty=format:%at %B',
                         '--follow', '--remove-empty',
                         '--max-count=1', '--skip={}'.format(skip),
                         '--', filename)
        ts, sep, log_message = output.partition(' ')
        if not sep:
            return None
        elif not is_ignored(log_message):
            return int(ts)


def _is_dirty(filename):
    status = run_git('status', '-z', '--', filename)
    return status != ''


def get_mtime(filename, ignore_commits=None):
    if _is_dirty(filename):
        return _fs_mtime(filename)
    mtime = _git_mtime(filename, ignore_commits)
    return mtime if mtime is not None else _fs_mtime(filename)


class GitTimestampDescriptor(object):
    def __init__(self, ignore_commits=None):
        if ignore_commits is not None:
            if not hasattr(ignore_commits, 'search'):
                ignore_commits = re.compile(ignore_commits)
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
