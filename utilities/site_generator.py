#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

# Copyright (c) 2019 The ungoogled-chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
'''
Generates the website files
'''

import datetime
import os.path
import pathlib
import re
import shutil
import string
import sys

import markdown  # Python-Markdown: https://github.com/waylan/Python-Markdown
from pkg_resources.extern.packaging.version import Version as VersionSortKey

if __name__ == "__main__" and (__package__ is None or __package__ == ""):

    def _fix_relative_import():
        """Allow relative imports to work from anywhere"""
        parent_path = os.path.dirname(
            os.path.realpath(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.dirname(parent_path))
        global __package__  #pylint: disable=global-variable-undefined
        __package__ = os.path.basename(parent_path)  #pylint: disable=redefined-builtin
        __import__(__package__)
        sys.path.pop(0)

    _fix_relative_import()

from . import pyatom  # pylint: disable=wrong-import-position
from . import _config_parsing  # pylint: disable=wrong-import-position

_USER_NAME = 'ungoogled-software'
_REPOSITORY_NAME = 'ungoogled-chromium-binaries'
_HOMEPAGE_URL = 'https://{user}.github.io/{repo}/'.format(
    user=_USER_NAME, repo=_REPOSITORY_NAME)
_FEED_FILE = 'feed.xml'
_ABSOLUTE_URL_PREFIX = "/{}/".format(_REPOSITORY_NAME)

_CONFIG = pathlib.Path("config")
_PAGE_TEMPLATES = _CONFIG / pathlib.Path("page_templates")
_INPUT_SUFFIX = ".md"
_OUTPUT_SUFFIX = ".html"
_INDEX_FRONTPAGE = _PAGE_TEMPLATES / pathlib.Path("index_frontpage" +
                                                  _INPUT_SUFFIX + ".in")
_INDEX_DIRECTORY = _PAGE_TEMPLATES / pathlib.Path("index_directory" +
                                                  _INPUT_SUFFIX + ".in")
_OUTPUT_WRAPPER = _PAGE_TEMPLATES / pathlib.Path("output_wrapper" +
                                                 _OUTPUT_SUFFIX + ".in")
_OUTPUT_INDEX = pathlib.Path("index" + _OUTPUT_SUFFIX)
_VERSION_INPUT = _PAGE_TEMPLATES / pathlib.Path("version" + _INPUT_SUFFIX +
                                                ".in")
_PLATFORMS = _CONFIG / pathlib.Path("platforms")
_RELEASES = pathlib.Path("releases")
_DISPLAY_NAME = pathlib.Path("display_name")
_INSTALL_INFO = pathlib.Path("install_info")

# For printing out info and Markdown
_INDENTATION = "    "

_FEED_CONTENT_TEMPLATE = '''<h2>Release Summary</h2>
<p>
<div>Author: {author}</div>
<div>Number of files: {file_count}</div>
</p>'''


class PageFileStringTemplate(string.Template):
    '''
    Custom string substitution class

    Inspired by
    http://stackoverflow.com/questions/12768107/string-substitutions-using-templates-in-python
    '''

    pattern = r"""
    {delim}(?:
      (?P<escaped>{delim}) |
      _(?P<named>{id})      |
      {{(?P<braced>{id})}}   |
      (?P<invalid>{delim}((?!_)|(?!{{)))
    )
    """.format(
        delim=re.escape("$ungoog"), id=string.Template.idpattern)


class PlatformVersion:
    def __init__(self, config_path, parent):
        if not config_path.is_file():
            raise FileNotFoundError(str(config_path))
        self._real_path = config_path
        self.path = self._real_path.relative_to(
            _PLATFORMS).parent / self._real_path.stem
        self.parent = parent
        self.version = self.path.name
        self.display_name = self.version

        (self.files, self.publication_time, self.github_author,
         self.install_info, self.note) = _config_parsing.parse_version_ini(
             self._real_path)

    def __lt__(self, other):
        return self.version < other.version

    def __str__(self):
        return "A Version: {}".format(str(self.version))

    def __repr__(self):
        return str(self)


def _version_sorting_key(ini_path):
    version_without_dashes = ini_path.stem.replace("-", ".")
    version_without_characters = re.sub(r'[a-zA-Z]', '', version_without_dashes)

    """
    Returns a comparable object representing the sorting key for the INI path
    """
    return VersionSortKey(version_without_characters)


class PlatformDirectory:
    def __init__(self, dir_path, parent):
        if not dir_path.is_dir():
            raise NotADirectoryError(str(dir_path))
        self._real_path = dir_path
        self.path = self._real_path.relative_to(_PLATFORMS)
        self.parent = parent
        self.children = list()
        self.versions = list()  # Latest version is first

        with (dir_path / _DISPLAY_NAME).open() as display_name_file:
            self.display_name = display_name_file.read().splitlines()[0]

        self.install_info = None
        if (dir_path / _INSTALL_INFO).exists():
            self.install_info = (dir_path / _INSTALL_INFO).read_text().strip()

        for config_path in sorted(
                self._real_path.glob("*.ini"),
                key=_version_sorting_key,
                reverse=True):
            print("Parsing version ini: {}".format(str(config_path)))
            new_version = PlatformVersion(config_path, self)
            self.versions.append(new_version)

    def __lt__(self, other):
        return self.path < other.path

    def recursively_read_children(self):
        for entry in self._real_path.iterdir():
            if entry.is_dir():
                tmp_dir = PlatformDirectory(entry, self)
                tmp_dir.recursively_read_children()
                self.children.append(tmp_dir)
        self.children.sort()

    @property
    def latest_version(self):
        if not self.versions:
            return None
        return self.versions[0]

    def __str__(self):
        return "Directory: {}".format(str(self.path))

    def __repr__(self):
        return str(self)


def read_config():
    root_dir = PlatformDirectory(_PLATFORMS, None)
    root_dir.name = _RELEASES.name
    root_dir.recursively_read_children()
    return root_dir


def preorder_traversal(root_dir, include_versions=False):
    stack = list()
    stack.append(root_dir)
    while len(stack) > 0:
        directory = stack.pop()
        yield directory
        if include_versions:
            for version in directory.versions:
                yield version
        for child in sorted(directory.children, reverse=True):
            stack.append(child)


def print_config(root_dir):
    for node in preorder_traversal(root_dir, include_versions=True):
        for i in range(len(node.path.parts)):
            print(_INDENTATION, end="")
        print(node.display_name, end="")
        if isinstance(node, PlatformDirectory):
            print()
        elif isinstance(node, PlatformVersion):
            indentation_amt = len(node.path.parts)
            print()
            for filename in sorted(node.files):
                for i in range(indentation_amt + 1):
                    print(_INDENTATION, end="")
                print(filename)
        else:
            print("Unknown node ", node)


def _get_node_weburl(node, prefix=_ABSOLUTE_URL_PREFIX):
    # Hacky
    return prefix + _RELEASES.name + "/" + "/".join(node.path.parts)


def _write_output_file(target_path, md_content):
    page_subs = dict(
        title=md_content.splitlines()[0][1:].strip(),
        github_markdown_css=_ABSOLUTE_URL_PREFIX + "github-markdown.css",
        body=markdown.markdown(
            md_content,
            extensions=[
                "markdown.extensions.tables",
            ],
            output_format="xhtml5"))
    with _OUTPUT_WRAPPER.open() as input_file:
        content = PageFileStringTemplate(
            input_file.read()).substitute(**page_subs)
    with target_path.open("w") as output_file:
        output_file.write(content)


def _write_frontpage_index(root_dir):
    target_path = _OUTPUT_INDEX

    download_markdown = str()

    download_markdown += 'Platform|Latest version\n'
    download_markdown += ':--|:--\n'  # Define table columns and alignment
    for node in preorder_traversal(root_dir):
        if node == root_dir or not node.versions:
            continue
        download_markdown += "**[{}]({})**".format(
            " ".join(_get_display_names(node)), _get_node_weburl(node))
        download_markdown += "|"
        current_version = node.latest_version
        if not current_version:
            raise ValueError("Node has no latest version: {}".format(
                _get_display_names(node)))
        download_markdown += "[{}]({})".format(
            current_version.version, _get_node_weburl(current_version))
        download_markdown += "\n"

    page_subs = dict(latest_downloads=download_markdown)
    with _INDEX_FRONTPAGE.open() as input_file:
        content = PageFileStringTemplate(
            input_file.read()).substitute(**page_subs)
    _write_output_file(target_path, content)


def _write_directory_index(directory_node):
    target_path = _RELEASES / directory_node.path / _OUTPUT_INDEX

    markdown_urls = list()
    current_node = directory_node
    while not current_node is None:
        markdown_urls.insert(
            0, "[{}]({})".format(current_node.display_name,
                                 _get_node_weburl(current_node)))
        current_node = current_node.parent
    markdown_urls.insert(0, "[Front page]({})".format(_ABSOLUTE_URL_PREFIX))

    versions_list_markdown = str()
    if len(directory_node.versions) > 0:
        versions_list_markdown = "## Available versions\n\n"
        for version in directory_node.versions:
            versions_list_markdown += "* [{}]({})\n".format(
                version.version, _get_node_weburl(version))

    directory_list_markdown = str()
    if len(directory_node.children) > 0:
        directory_list_markdown = "## Subgroupings\n\n"
        for subdirectory in directory_node.children:
            directory_list_markdown += "* [{}]({})\n".format(
                subdirectory.display_name, _get_node_weburl(subdirectory))

    page_subs = dict(
        current_path=" / ".join(markdown_urls),
        versions_list=versions_list_markdown,
        directory_list=directory_list_markdown)
    with _INDEX_DIRECTORY.open() as input_file:
        content = PageFileStringTemplate(
            input_file.read()).substitute(**page_subs)
    _write_output_file(target_path, content)


def _get_display_names(node):
    display_names = list()
    if isinstance(node, PlatformVersion):
        current_node = node.parent
    elif isinstance(node, PlatformDirectory):
        current_node = node
    else:
        raise ValueError("Unknown node type {}".format(type(node).__name__))
    while not current_node.parent is None:
        display_names.insert(0, current_node.display_name)
        current_node = current_node.parent
    return display_names


def _write_version_page(version_node):
    target_path = _RELEASES / version_node.path.parent / (
        version_node.version + _OUTPUT_SUFFIX)

    markdown_urls = list()
    install_info = None
    current_node = version_node
    while not current_node is None:
        markdown_urls.insert(
            0, "[{}]({})".format(current_node.display_name,
                                 _get_node_weburl(current_node)))
        if not install_info and current_node.install_info:
            install_info = current_node.install_info
        current_node = current_node.parent
    if not install_info:
        install_info = "*(unspecified)*"
    markdown_urls.insert(0, "[Front page]({})".format(_ABSOLUTE_URL_PREFIX))

    if version_node.publication_time:
        publication_time_markdown = '`{}`'.format(
            version_node.publication_time.isoformat(sep=' '))
    else:
        publication_time_markdown = '*(unspecified)*'
    if version_node.github_author:
        if version_node.github_author == 'github-actions':
            url = list(version_node.files.values())[0][0]
            github_repo_url = re.sub(r'\/releases\/.+', '', url)

            github_author_markdown = '[GitHub Actions]({url})'.format(url=github_repo_url + '/actions')
        else:
            github_author_markdown = '[{author}](//github.com/{author}) ([view all releases from user](//github.com/{author}/{repository}/releases))'.format(
                author=version_node.github_author, repository=_REPOSITORY_NAME)
    else:
        github_author_markdown = '*(unspecified)*'
    note_markdown = version_node.note

    download_list_markdown = str()
    for filename in sorted(version_node.files.keys()):
        url, hashes = version_node.files[filename]
        download_list_markdown += "* [{}]({})\n".format(filename, url)
        for hashname in sorted(hashes.keys()):
            download_list_markdown += _INDENTATION + "* {}: `{}`\n".format(
                hashname, hashes[hashname])

    page_subs = dict(
        version=version_node.version,
        display_name=" ".join(_get_display_names(version_node)),
        current_path=" / ".join(markdown_urls),
        author=github_author_markdown,
        publication_time=publication_time_markdown,
        install_info=install_info,
        note=note_markdown,
        download_list=download_list_markdown)
    with _VERSION_INPUT.open() as input_file:
        content = PageFileStringTemplate(
            input_file.read()).substitute(**page_subs)
    _write_output_file(target_path, content)


def _add_node_to_feed(feed, node_feed):
    display_name = ' '.join(_get_display_names(node_feed))
    if node_feed.publication_time:
        feed_id = node_feed.publication_time.isoformat()
        updated_datetime = node_feed.publication_time
    else:
        feed_id = 'unspecified'
        updated_datetime = datetime.datetime(
            1, 1, 1, tzinfo=datetime.timezone.utc)
    feed_id += node_feed.version
    feed_id += display_name.replace(" ", '')
    feed.add(
        title='{platform}: {version}'.format(
            platform=display_name,
            version=node_feed.version,
        ),
        content=_FEED_CONTENT_TEMPLATE.format(
            author=(node_feed.github_author or '(unspecified)'),
            file_count=len(node_feed.files)),
        content_type='html',
        updated=updated_datetime,
        url=_get_node_weburl(node_feed, prefix=_HOMEPAGE_URL),
        id=feed_id,
    )


def write_website(root_dir, feed_path):
    if _RELEASES.exists():
        if not _RELEASES.is_dir():
            raise NotADirectoryError(
                "The releases directory is not a directory")
        shutil.rmtree(str(_RELEASES))

    feed = pyatom.AtomFeed(
        title='ungoogled-chromium Binary Downloads',
        subtitle='Feed of contributor-submitted binaries',
        feed_url=_HOMEPAGE_URL + _FEED_FILE,
        url=_HOMEPAGE_URL)

    for node in preorder_traversal(root_dir, include_versions=True):
        if isinstance(node, PlatformDirectory):
            (_RELEASES / node.path).mkdir()
            _write_directory_index(node)
            if node.latest_version:
                _add_node_to_feed(feed, node.latest_version)
        elif isinstance(node, PlatformVersion):
            _write_version_page(node)
        else:
            print("Unknown node ", node)

    _write_frontpage_index(root_dir)
    with feed_path.open('w') as feed_file:
        feed_file.write(feed.to_string())


def main():
    root_dir = read_config()

    #print_config(root_dir)
    write_website(root_dir,
                  pathlib.Path(__file__).resolve().parent.parent / _FEED_FILE)


if __name__ == "__main__":
    main()
