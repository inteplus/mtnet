"""Network utilities: host info, host-port parsing, TCP port checking and port forwarding.

The package re-exports everything of its submodules:

- :mod:`mt.net.base` : :func:`get_hostname`, :func:`get_username`, :func:`is_port_open`,
  :func:`get_default_ifaces`, :func:`get_all_inet4_ipaddresses`, :func:`get_all_hosts_from_network`
  and :func:`get_public_ip_address`
- :mod:`mt.net.host_port` : :class:`HostPort` and :func:`listen_to_port`
- :mod:`mt.net.port_forwarding` : :func:`launch_port_forwarder`, using threads
- :mod:`mt.net.port_forwarding_async` : :func:`port_forwarder_actx`, using :mod:`asyncio`
- :mod:`mt.net.ssh_forwarding` : :func:`launch_ssh_forwarder`, via an SSH tunnel

Examples
--------
>>> from mt import net
>>> net.HostPort.from_str("localhost:8080").socket_address()
('localhost', 8080)
"""

from .base import *
from .host_port import *
from .port_forwarding import *
from .port_forwarding_async import *
from .ssh_forwarding import *
from .version import version as __version__


__api__ = [
    "get_default_ifaces",
    "is_port_open",
    "get_hostname",
    "get_username",
    "get_all_hosts_from_network",
    "get_all_inet4_ipaddresses",
    "get_public_ip_address",
    "HostPort",
    "listen_to_port",
    "set_keepalive_linux",
    "set_keepalive_osx",
    "launch_port_forwarder",
    "port_forwarder_actx",
    "SSHTunnelWatcher",
    "launch_ssh_forwarder",
]


# check if mtnet has been installed
def _future_warn_install_mtnet():
    """Warns the user to install package `mtnet`, if it is not installed.

    It looks for `mtnet` in the output of `pip freeze`. It is currently not invoked.
    """
    import subprocess as sp

    bash_str = 'pip freeze | grep "mtnet"'
    try:
        sp.check_output(bash_str, shell=True)
    except sp.CalledProcessError:
        from .. import logg

        logg.logger.warn(
            "The 'mt.net' section of package 'mtbase' will be moved to package 'mtnet' "
            "from version 5.0."
        )
        logg.logger.warn("Please pip install mtnet in advance to avoid disruptions.")


# MT-NOTE: I commented out the following statement: _future_warn_install_mtnet()
