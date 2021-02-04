# -*- coding: utf-8 -*-
from collections import namedtuple
import datetime
import hashlib
from operator import attrgetter
import os
import pickle
import re
import subprocess

import jinja2
from lektor.context import get_ctx
from lektor.pluginsystem import Plugin
from lektor.reporter import reporter
from lektor.sourceobj import VirtualSourceObject
from lektor.types import DateTimeType
from lektor.utils import bool_from_string
from werkzeug.utils import cached_property

from lektorlib.recordcache import get_or_create_virtual

VIRTUAL_PATH_PREFIX = 'git-timestamp'


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


def get_mtime(timestamps,
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

    filtered = list(filter(is_not_ignored, timestamps))
    if skip_first_commit:
        filtered = filtered[:-1]

    if len(filtered) == 0:
        return None
    elif strategy == 'first':
        return filtered[-1].ts
    elif strategy == 'earliest':
        return min(map(attrgetter('ts'), filtered))
    elif strategy == 'latest':
        return max(map(attrgetter('ts'), filtered))
    else:                       # strategy == 'last'
        return filtered[0].ts


def _compute_checksum(data):
    return hashlib.sha1(pickle.dumps(data, protocol=0)).hexdigest()


class GitTimestampSource(VirtualSourceObject):
    @classmethod
    def get(cls, record):
        def creator():
            return cls(record)
        return get_or_create_virtual(record, VIRTUAL_PATH_PREFIX, creator)

    @property
    def path(self):
        return "{}@{}".format(self.record.path, VIRTUAL_PATH_PREFIX)

    def get_checksum(self, path_cache):
        return _compute_checksum(self.timestamps)

    @cached_property
    def timestamps(self):
        return tuple(_iter_timestamps(self.source_filename))


class GitTimestampDescriptor(object):
    def __init__(self, raw,
                 ignore_commits=None,
                 strategy='last',
                 skip_first_commit=False):
        self.raw = raw
        self.kwargs = {
            'ignore_commits': ignore_commits,
            'strategy': strategy,
            'skip_first_commit': skip_first_commit,
            }

    def __get__(self, obj, type_=None):
        if obj is None:
            return self
        ctx = get_ctx()
        src = GitTimestampSource.get(obj)
        if ctx:
            ctx.record_virtual_dependency(src)
        mtime = get_mtime(src.timestamps, **self.kwargs)
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
        env = self.env
        env.add_type(GitTimestampType)
        env.virtualpathresolver(VIRTUAL_PATH_PREFIX)(self.resolve_virtual_path)

    @staticmethod
    def resolve_virtual_path(record, pieces):
        if len(pieces) == 0:
            return GitTimestampSource.get(record)
