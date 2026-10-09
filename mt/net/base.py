"""Basic network helpers: host name, user name, network interfaces, host scanning, port checking.

Most functions depend on the machine they run on, and some of them need network access.

Examples
--------
>>> import socket
>>> from mt.net.base import is_port_open
>>> server = socket.socket()
>>> server.bind(("127.0.0.1", 0))
>>> server.listen(1)
>>> is_port_open("127.0.0.1", server.getsockname()[1])
True
>>> server.close()
"""

import socket
import psutil
import getpass
import netifaces
import ipaddress
import requests
import getmac


def get_default_ifaces():
    """Returns a list of (host_ip_addr, subnet, broadcast, gateway_ip_address, iface) tuples of
    default ifaces.

    The default gateways are queried with :mod:`netifaces`, and for each of them, the first address
    of
    the corresponding interface is used. Gateways for which the addresses cannot be parsed are
    skipped, and so are those whose interface address has no 'broadcast' entry (for example
    point-to-point interfaces).

    Returns
    -------
    list
        list of tuples `(host_ip_addr, subnet, broadcast, gateway_ip_address, iface)`, where the
        first
        four items are respectively an :class:`ipaddress.IPv4Address` (or IPv6), an
        :class:`ipaddress.IPv4Network`, and two more IP addresses, and `iface` is the name of the
        interface as a string
    """
    res = []
    for k, v in netifaces.gateways()["default"].items():
        try:
            gw, iface = v
            item = netifaces.ifaddresses(iface)[k][0]
            ip_addr = ipaddress.ip_address(item["addr"])
            net_str = f"{item['addr']}/{item['netmask']}"
            ip_network = ipaddress.ip_network(net_str, strict=False)
            gw_addr = ipaddress.ip_address(gw)
            bc_addr = ipaddress.ip_address(item["broadcast"])
            res.append((ip_addr, ip_network, bc_addr, gw_addr, iface))
        except (ValueError, KeyError):
            continue
    return res


def is_port_open(addr, port, timeout=2.0):
    """Checks if a port is open, with timeout.

    The function tries to make a TCP connection over IPv4 to the port.

    Parameters
    ----------
    addr : str
        ip address, hostname or fqdn
    port : int
        port number
    timeout : float, optional
        timeout in seconds. Default is 2.0.

    Returns
    -------
    bool
        whether or not the port at the given address is open. Any error, including a timeout or a
        name that cannot be resolved, is reported as False.

    Examples
    --------
    >>> import socket
    >>> from mt.net import is_port_open
    >>> server = socket.socket()
    >>> server.bind(("127.0.0.1", 0))
    >>> port = server.getsockname()[1]
    >>> server.listen(1)
    >>> is_port_open("127.0.0.1", port)
    True
    >>> server.close()
    >>> is_port_open("127.0.0.1", port, timeout=0.5)
    False
    """

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((addr, port))
        return result == 0
    except:
        return False


def get_hostname():
    """Returns the machine's hostname.

    Returns
    -------
    str
        the host name, as returned by :func:`socket.gethostname`
    """
    return socket.gethostname()


def get_username():
    """Returns the current username.

    Returns
    -------
    str
        the current username, as returned by :func:`getpass.getuser`
    """
    return getpass.getuser()


def get_all_hosts_from_network(ip_network):
    """Gets all hosts (ip_addr, mac_addr) from a given ip network.

    Every host address of the network is looked up with :mod:`getmac`, which can be slow for a large
    network. Addresses without a MAC address, or with an all-zero one, are skipped.

    Parameters
    ----------
    ip_network : ipaddress.IPv4Network
        IP network

    Returns
    -------
    list
        list of (ip_addr -> ipaddress.IPv4Address, mac_addr -> str) pairs of detected hosts in the
        subnet.
    """
    res = []
    for addr in ip_network.hosts():
        mac = getmac.get_mac_address(ip=addr.exploded)
        if mac is not None and mac != "00:00:00:00:00:00":
            res.append((addr, mac))

    return res


def get_all_inet4_ipaddresses():
    """Returns all network INET4 interfaces' IP addresses+netmasks.

    Returns
    -------
    dict
        A dictionary of interface_name -> (ip_address, netmask), where both addresses are strings.
        Only the first IPv4 address of each interface is reported, and interfaces without an IPv4
        address are omitted.
    """
    retval1 = psutil.net_if_addrs()
    retval2 = {}
    for k, v in retval1.items():
        for e in v:
            if e.family == socket.AF_INET:
                retval2[k] = (e.address, e.netmask)
                break

    return retval2


def get_public_ip_address():
    """Obtains the public IP address using AWS.

    It sends an HTTPS request to `https://checkip.amazonaws.com`, so it needs internet access.

    Returns
    -------
    ipaddress.IPv4Address or ipaddress.IPv6Address
        public ip address of the current host

    Raises
    ------
    requests.exceptions.RequestException
        if the request fails
    ValueError
        if the response is not an IP address
    """
    ip = requests.get("https://checkip.amazonaws.com").text.strip()
    return ipaddress.ip_address(ip)
