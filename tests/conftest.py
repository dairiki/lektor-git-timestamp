# -*- coding: utf-8 -*-

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
