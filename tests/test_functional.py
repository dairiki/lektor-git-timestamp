# -*- coding: utf-8 -*-
import datetime
try:
    from pathlib import Path
except ImportError:
    # python < 3.4
    from pathlib2 import Path
import shutil

import jinja2
import lektor.metaformat
import lektor.project
import pytest
from six import text_type


@pytest.fixture
def project(tmp_path):
    site_src = Path(__file__).parent / 'test-site'
    site_path = tmp_path / 'site'
    shutil.copytree(text_type(site_src), text_type(site_path))
    return lektor.project.Project.from_path(str(site_path))


@pytest.fixture
def env(project):
    return project.make_env(load_plugins=True)


@pytest.fixture(scope='session')
def now():
    return datetime.datetime.now().replace(microsecond=0)


@pytest.fixture
def pub_date(now):
    return now - datetime.timedelta(hours=3)


@pytest.fixture
def last_mod(now):
    return now - datetime.timedelta(hours=1)


def write_data(filename, data):
    """ Write lektor .lr serialized data."""
    with open(filename, "wb") as f:
        for chunk in lektor.metaformat.serialize(data, encoding="utf-8"):
            f.write(chunk)


def test_pub_date_for_untracked_file(git_repo, pad, pub_date):
    git_repo.touch('site/content/contents.lr', pub_date)
    assert pad.root['pub_date'] == pub_date
    assert jinja2.is_undefined(pad.root['last_mod'])


def test_explicit_pub_date(git_repo, pad, pub_date, now):
    write_data("site/content/contents.lr", [
        ('pub_date', pub_date.isoformat(' ')),
    ])
    git_repo.commit('site/content/contents.lr', now)
    assert pad.root['pub_date'] == pub_date


def test_last_mod_ignores_initial_commit(git_repo, pad, pub_date):
    git_repo.commit('site/content/contents.lr', pub_date)
    assert pad.root['pub_date'] == pub_date
    assert jinja2.is_undefined(pad.root['last_mod'])


def test_last_mod(git_repo, pad, pub_date, last_mod):
    git_repo.commit('site/content/contents.lr', pub_date)
    first_mod = last_mod - datetime.timedelta(minutes=30)
    git_repo.commit('site/content/contents.lr', first_mod)
    git_repo.commit('site/content/contents.lr', last_mod)
    assert pad.root['pub_date'] == pub_date
    assert pad.root['last_mod'] == last_mod


def test_pub_date_ignores_nochange(git_repo, pad, pub_date, now):
    ignored_date = pub_date - datetime.timedelta(minutes=5)
    git_repo.commit('site/content/contents.lr', ignored_date,
                    message="Ignore this commit [nochange]")
    git_repo.commit('site/content/contents.lr', pub_date)
    git_repo.commit('site/content/contents.lr', now,
                    message="Also ignore this commit [nochange]")
    assert pad.root['pub_date'] == pub_date
    assert jinja2.is_undefined(pad.root['last_mod'])


def test_last_mod_ignores_nochange(git_repo, pad, pub_date, last_mod, now):
    git_repo.commit('site/content/contents.lr', pub_date)
    git_repo.commit('site/content/contents.lr', last_mod)
    git_repo.commit('site/content/contents.lr', now, message="test [nochange]")
    assert pad.root['pub_date'] == pub_date
    assert pad.root['last_mod'] == last_mod


def test_last_mod_for_dirty_file(git_repo, pad, pub_date, last_mod, now):
    git_repo.commit('site/content/contents.lr', pub_date)
    git_repo.commit('site/content/contents.lr', last_mod)
    git_repo.modify('site/content/contents.lr', now)
    assert pad.root['pub_date'] == pub_date
    assert pad.root['last_mod'] == now
