#!/usr/bin/env python3

import os
import argparse
from getpass import getuser
import subprocess as sp


def main(args):
    user = args.user if args.user else getuser()
    pipi_url = f"https://localhost:5443/repository/{user}-pypi-dev/simple/"
    pip_command = ["wml_nexus.py", "uv", "pip", "install"]
    if os.getuid() == 0:
        pip_command += ["-p", "/usr/bin/python3", "--system", "--break-system-packages"]
    else:
        pip_command += []  # ["--prerelease", "allow"]
    pip_command += [
        "--allow-insecure-host",
        "localhost",
        "--index",
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
        help="Install packages from the nexus repo of a given user. If not, the current user's nexus repo is used.",
    )
    args.add_argument(
        "-U",
        "--upgrade",
        action="store_true",
        help="Upgrade all specified packages to the newest available version. The handling of dependencies depends on the upgrade-strategy used.",
    )
    args.add_argument("packages", nargs="*", help="Packages to install via pip.")
    parsed_args = args.parse_args()
    main(parsed_args)
