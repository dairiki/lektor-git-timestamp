# -*- coding: utf-8 -*-
from collections import namedtuple
import datetime
from operator import attrgetter
import os
import re
import subprocess

import jinja2
from lektor.pluginsystem import Plugin
from lektor.reporter import reporter
from lektor.types import DateTimeType
from lektor.utils import bool_from_string


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


def get_mtime(filename,
              ignore_commits=None,
              strategy='last',
              skip_first_commit=False):
    def is_not_ignored(timestamp):
        if ignore_commits is None:
            return True
        message = timestamp.commit_message
        if message is None:
            return True
        return re.search(ignore_commits, message) is None

    timestamps = list(filter(is_not_ignored, _iter_timestamps(filename)))
    if skip_first_commit:
        timestamps = timestamps[:-1]

    if len(timestamps) == 0:
        return None
    elif strategy == 'first':
        return timestamps[-1].ts
    elif strategy == 'earliest':
        return min(map(attrgetter('ts'), timestamps))
    elif strategy == 'latest':
        return max(map(attrgetter('ts'), timestamps))
    else:                       # strategy == 'last'
        return timestamps[0].ts


class GitTimestampDescriptor(object):
    def __init__(self, raw,
                 ignore_commits=None,
                 strategy='last',
                 skip_first_commit=False):
        self.raw = raw
        self.kwargs = {
            'ignore_commits': ignore_commits,
            'strategy': timestamp,
            'skip_first_commit': skip_first_commit,
            }

    def __get__(self, obj, type_=None):
        if obj is None:
            return self
        mtime = get_mtime(obj.source_filename, **self.kwargs)
        if mtime is None:
            return self.raw.missing_value("no suitable git timestamp exists")
        return datetime.datetime.fromtimestamp(mtime)


class GitTimestampType(DateTimeType):
    def value_from_raw(self, raw):
        value = super(GitTimestampType, self).value_from_raw(raw)
        if jinja2.is_undefined(value):
            options = self.options
            value = GitTimestampDescriptor(
                raw,
                ignore_commits=options.get('ignore_commits'),
                strategy=options.get('strategy', 'last'),
                skip_first_commit=bool_from_string(
                    options.get('skip_first_commit', False)),
                )
        return value


class GitTimestampPlugin(Plugin):
    name = 'git-timestamp'
    description = u'Lektor type to deduce page modification time from git'

    def on_setup_env(self, **extra):
        self.env.add_type(GitTimestampType)
