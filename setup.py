#!/usr/bin/env python3

from setuptools import setup, find_namespace_packages

install_requires = [
    "mtbase>=4.2",  # awaiting mtbase to upgrade to 5.0
]

setup(
    name="mtnet",
    version="0.0",
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
