#!/usr/bin/env python3

from setuptools import setup, find_namespace_packages

from mt.base.version import version

install_requires = [
    "mtbase>=4.5",  # mtbase without mt.net
    "getmac<0.9",  # a bug at getmac>=0.9 is stopping us from using get_mac_address properly
    "netifaces",
    "sshtunnel",  # for ssh tunnelling
]

setup(
    name="mtnet",
    version=version,
    description="The most fundamental Python modules for Minh-Tri Pham",
    author=["Minh-Tri Pham"],
    packages=find_namespace_packages(include=["mt.*"]),
    install_requires=install_requires,
    url="https://github.com/inteplus/mtnet",
    project_urls={
        "Documentation": "https://mtdoc.readthedocs.io/en/latest/mt.net/mt.net.html",
        "Source Code": "https://github.com/inteplus/mtnet",
    },
)
