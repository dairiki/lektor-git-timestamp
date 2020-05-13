# -*- coding: utf-8 -*-
import datetime
from itertools import count
import os
import re
import subprocess

from more_itertools import windowed

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
    #
    # XXX: Originally I tried fetching the timestamp for
    # one commit at a time (--max-count=1) using --skip
    # to skip back through history to find the first non-ignored
    # commit.  That was not working reliably.
    # --skip with --follow seems to do unexpected things —
    # or at least things which I don’t current understand.
    #
    # This iterative searching of commits could be avoided by using
    # `git log --invert-grep --grep=<ignore>`, however this requires
    # git >= 2.4.0 (which is not easily available on my old Debian
    # Jessie machine)

    def is_ignored(log_message):
        if ignore_commits is None:
            return False
        return re.search(ignore_commits, log_message) is not None

    for prev_n, n in windowed([0, 1, 3, 8, 32, None], 2):
        git_args = ['log',
                    '--pretty=format:%at %B', '-z',
                    '--follow', '--remove-empty',
                    '--', filename]
        if n is not None:
            git_args.insert(-2, '--max-count={}'.format(n))
        output = run_git(*git_args).split('\0')
        for line in output[prev_n:]:
            ts, sep, log_message = line.partition(' ')
            if not sep:
                return None
            elif not is_ignored(log_message):
                return int(ts)
        if len(output) < n:
            return None


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
