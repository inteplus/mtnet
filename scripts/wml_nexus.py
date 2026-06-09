#!/usr/bin/env python3

import asyncio
import sys
import subprocess

from mt import net, logg


def execute(argv):
    res = subprocess.run(argv[1:], shell=False, check=False)
    sys.exit(res.returncode)


async def main():
    argv = sys.argv
    logg.logger.setLevel(logg.INFO)

    if len(argv) < 2:
        print("Opens localhost:5443 as nexus https and runs a command.")
        print("Syntax: {} cmd arg1 arg2 ...".format(argv[0]))
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
