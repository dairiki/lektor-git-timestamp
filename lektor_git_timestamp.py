# -*- coding: utf-8 -*-
import datetime
import os
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


def _git_mtime(filename):
    ts = run_git('log', '--pretty=format:%at', '--follow', '--max-count=1',
                 '--', filename)
    return int(ts) if ts else None


def _is_dirty(filename):
    status = run_git('status', '-z', '--', filename)
    return status != ''


def get_mtime(filename):
    if _is_dirty(filename):
        return _fs_mtime(filename)
    mtime = _git_mtime(filename)
    return mtime if mtime is not None else _fs_mtime(filename)


class GitTimestampDescriptor(object):
    def __init__(self, type_):
        self.type_ = type_

    def __get__(self, obj, type_=None):
        if obj is None:
            return self
        mtime = max(map(get_mtime, obj.iter_source_filenames()))
        return datetime.datetime.fromtimestamp(mtime)


class GitTimestampType(DateTimeType):
    def value_from_raw(self, raw):
        value = super(GitTimestampType, self).value_from_raw(raw)
        if jinja2.is_undefined(value):
            value = GitTimestampDescriptor(self)
        return value


class GitTimestampPlugin(Plugin):
    name = 'git-timestamp'
    description = u'Lektor type to deduce page modification time from git'

    def on_setup_env(self, **extra):
        self.env.add_type(GitTimestampType)
