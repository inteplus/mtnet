#!/usr/bin/env python3

import os
from setuptools import setup, find_namespace_packages

VERSION_FILE = os.path.join(os.path.dirname(__file__), "VERSION.txt")

install_requires = [
    "mtbase>=4.32.1",  # just updating
    "getmac<0.9",  # a bug at getmac>=0.9 is stopping us from using get_mac_address properly
    "netifaces",
    "requests",
    "sshtunnel",  # for ssh tunnelling
]

setup(
    name="mtnet",
    description="The most fundamental Python modules for Minh-Tri Pham",
    author=["Minh-Tri Pham"],
    packages=find_namespace_packages(include=["mt.*"]),
    install_requires=install_requires,
    url="https://github.com/inteplus/mtnet",
    project_urls={
        "Documentation": "https://mtdoc.readthedocs.io/en/latest/mt.net/mt.net.html",
        "Source Code": "https://github.com/inteplus/mtnet",
    },
    setup_requires=["setuptools-git-versioning<2"],
    setuptools_git_versioning={
        "enabled": True,
        "version_file": VERSION_FILE,
        "count_commits_from_version_file": True,
        "template": "{tag}",
        "dev_template": "{tag}.dev{ccount}+{branch}",
        "dirty_template": "{tag}.post{ccount}",
    },
)
