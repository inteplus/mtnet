#!/usr/bin/env python3

import os
from setuptools import setup, find_namespace_packages

VERSION_FILE = os.path.join(os.path.dirname(__file__), "VERSION.txt")

install_requires = [
    "mtbase>=4.33.27",  # just updating
    "getmac<0.9",  # a bug at getmac>=0.9 is stopping us from using get_mac_address properly
    "netifaces",
    "requests",
    "sshtunnel",  # for ssh tunnelling
]

setup(
    name="mtnet",
    description="The most fundamental Python modules for Minh-Tri Pham",
    author="Minh-Tri Pham",
    packages=find_namespace_packages(include=["mt.*"]),
    install_requires=install_requires,
    scripts=[
        "scripts/wml_nexus.py",  # for accessing Winnow Nexus repo
        "scripts/pipi.sh",  # for pip-installing packages using uv
        "scripts/wml_pipi.sh",  # for pip-installing packages using uv and Winnow Nexus repo
        "scripts/user_pipi.py",  # for pip-installing packages using uv and user-specific Winnow Nexus repo
        "scripts/dmt_pipi.sh",  # for pip-installing packages using uv and Winnow Nexus repo, MT dev environment
        "scripts/wml_twineu.sh",  # for uploading wheels to Winnow Nexus repo
        "scripts/user_twineu.sh",  # for uploading wheels to user-specific Winnow Nexus repo
        "scripts/dmt_twineu.sh",  # for uploading wheels to Winnow Nexus repo, MT dev environment
        "scripts/wml_build_package_and_upload_to_nexus.sh",  # for building package and uploading wheel to Winnow Nexus repo
        "scripts/user_build_package_and_upload_to_nexus.sh",  # for building package and uploading wheel to user-specific Winnow Nexus repo
        "scripts/dmt_build_package_and_upload_to_nexus.sh",  # for building package and uploading wheel to Winnow Nexus repo, MT dev environment
    ],
    url="https://github.com/inteplus/mtnet",
    project_urls={
        "Documentation": "https://mtdoc.readthedocs.io/en/latest/mt.net/mt.net.html",
        "Source Code": "https://github.com/inteplus/mtnet",
    },
    setup_requires=["setuptools-git-versioning>=3,<4"],
    setuptools_git_versioning={
        "enabled": True,
        "version_file": VERSION_FILE,
        "count_commits_from_version_file": True,
        "template": "{tag}",
        "dev_template": "{tag}",
        "dirty_template": "{tag}",
    },
)
