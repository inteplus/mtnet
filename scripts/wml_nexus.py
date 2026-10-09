#!/usr/bin/env python3

"""Runs a command with `localhost:5443` forwarded to the Nexus https server of Winnow.

Usage: `wml_nexus.py cmd arg1 arg2 ...`

If port 5443 of the localhost is already open, the command is simply run. Otherwise a port
forwarder from `:5443` to the first reachable Nexus endpoint is started for the duration of the
command. The exit code of the command is the exit code of this script.
"""

import asyncio
import sys
import subprocess

from mt import net, logg


def execute(argv):
    """Runs a command and exits with its return code.

    Parameters
    ----------
    argv : list
        the full command line, whose first item is the name of this script and the rest is the
        command
        to run
    """
    res = subprocess.run(argv[1:], shell=False, check=False)
    sys.exit(res.returncode)


async def main():
    """Forwards port 5443 to a reachable Nexus endpoint and runs the command in `sys.argv[1:]`.

    The endpoints are tried in order. The script exits with the return code of the command, or with
    code 1 if no endpoint can be reached. If no command is given, it prints the syntax and exits.
    """
    argv = sys.argv
    logg.logger.setLevel(logg.INFO)

    if len(argv) < 2:
        print("Opens localhost:5443 as nexus https and runs a command.")
        print(f"Syntax: {argv[0]} cmd arg1 arg2 ...")
        sys.exit(0)

    if net.is_port_open("localhost", 5443, timeout=0.1):
        execute(argv)

    l_endpoints = [
        ("192.168.110.4", 443),
        ("nexus.winnow.tech", 443),
        ("172.17.0.1", 5443),
    ]

    for host, port in l_endpoints:
        if not net.is_port_open(host, port):
            continue

        server = await net.port_forwarder_actx(
            ":5443", [f"{host}:{port}"], logger=logg.logger
        )
        async with server:
            process = await asyncio.create_subprocess_exec(*argv[1:])
            returncode = await process.wait()
            sys.exit(returncode)

    logg.logger.error("Unable to connect to nexus.")
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
