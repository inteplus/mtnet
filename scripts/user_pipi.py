#!/usr/bin/env python3

"""Installs packages from the user-specific Nexus pypi repository of Winnow, using `uv pip`.

Usage: `user_pipi.py [-u USER] [-U] package [package ...]`
"""

import os
import argparse
from getpass import getuser
import subprocess as sp


def main(args):
    """Runs `uv pip install` for the packages, with the user's Nexus pypi repository as an index.

    Parameters
    ----------
    args : argparse.Namespace
        parsed arguments, with attributes `user` (str or None, the Nexus user, defaulting to the
        current user), `upgrade` (bool, whether to pass `--upgrade`) and `packages` (list of str,
        the
        packages to install). When run as root, the packages are installed system-wide.

    Returns
    -------
    subprocess.CompletedProcess
        the result of running the command. A failing command raises
        :class:`subprocess.CalledProcessError`.
    """
    user = args.user if args.user else getuser()
    pipi_url = f"https://nexus.winnow.tech/repository/{user}-pypi-dev/simple/"
    pip_command = ["uv", "pip", "install"]
    if os.getuid() == 0:
        pip_command += ["-p", "/usr/bin/python3", "--system", "--break-system-packages"]
    else:
        pip_command += []  # ["--prerelease", "allow"]
    pip_command += [
        "--allow-insecure-host",
        pipi_url,
        "--index-strategy",
        "unsafe-best-match",
        "--link-mode=copy",
    ]
    if args.upgrade:
        pip_command += ["--upgrade"]
    pip_command += args.packages
    print("Pypi URL:", pipi_url)
    print("Running command:", " ".join(pip_command))
    return sp.run(pip_command, check=True)


if __name__ == "__main__":
    args = argparse.ArgumentParser(
        description="User-specific pip installer for wml packages."
    )
    args.add_argument(
        "-u",
        "--user",
        default=None,
        type=str,
        help="Install packages from the nexus repo of a given user. "
        "If not, the current user's nexus repo is used.",
    )
    args.add_argument(
        "-U",
        "--upgrade",
        action="store_true",
        help="Upgrade all specified packages to the newest available version. "
        "The handling of dependencies depends on the upgrade-strategy used.",
    )
    args.add_argument("packages", nargs="*", help="Packages to install via pip.")
    parsed_args = args.parse_args()
    main(parsed_args)
