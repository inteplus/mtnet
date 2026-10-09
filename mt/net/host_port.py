"""Host-port pairs and listening to a local port.

Examples
--------
>>> from mt.net import HostPort
>>> hp = HostPort.from_str("192.168.1.5:443")
>>> hp.socket_address()
('192.168.1.5', 443)
"""

import socket
from time import sleep
import re
import ipaddress

from mt import tp, logg


class HostPort:
    """Pair of host and port, where host can be by name or by ip address.

    The port must be given. As for the host, if an ip address is given, it has the priority. If
    not, the host name is taken. If even the host name is not provided, it is assumed that the host
    is localhost.

    Parameters
    ----------
    port : int
        the port number
    host_addr : ipaddress.IPv4Address or ipaddress.IPv6Address, optional
        the host address, if known
    host_name : str, optional
        the host name, if known. An empty string means all interfaces (the wildcard address) when
        listening.

    Attributes
    ----------
    port : int
        the port number
    host_addr : ipaddress.IPv4Address or ipaddress.IPv6Address or None
        the host address
    host_name : str or None
        the host name

    See Also
    --------
    from_str : creates an instance from a string like 'host:port'

    Examples
    --------
    >>> from mt.net import HostPort
    >>> HostPort(80).socket_address()
    ('localhost', 80)
    >>> HostPort(80, host_name="example.com").to_str()
    'example.com:80'
    """

    def __init__(
        self,
        port: int,
        host_addr: tp.Union[ipaddress.IPv4Address, ipaddress.IPv6Address, None] = None,
        host_name: tp.Optional[str] = None,
    ):
        self.port = port
        self.host_addr = host_addr
        self.host_name = host_name

    def is_v6(self):
        """Tells whether the host is an IPv6 one.

        Returns
        -------
        bool
            True if the host address is an IPv6 address or, when there is no address, if the host
            name
            contains a colon. False otherwise, including when no host is given.
        """
        if self.host_addr is None:
            if self.host_name is None:
                return False
            return ":" in self.host_name
        return isinstance(self.host_addr, ipaddress.IPv6Address)

    def socket_address(self) -> tp.Tuple[str, int]:
        """Returns the (addr, port) pair for socket programming.

        Returns
        -------
        tuple
            pair `(host, port)`. The host is the exploded form of the address if an address is
            given,
            else the host name, else 'localhost'. An empty host name stays empty, meaning all
            interfaces.

        Examples
        --------
        >>> from mt.net import HostPort
        >>> HostPort.from_str("::1:80").socket_address()
        ('0000:0000:0000:0000:0000:0000:0000:0001', 80)
        >>> HostPort.from_str(":30443").socket_address()
        ('', 30443)
        """

        if self.is_v6():
            if self.host_addr is None:
                return (self.host_name, self.port)
            return (self.host_addr.exploded, self.port)

        if self.host_addr is None:
            host_name = "localhost" if self.host_name is None else self.host_name
            return (host_name, self.port)

        return (self.host_addr.exploded, self.port)

    def to_str(self) -> str:
        """Serializes to a string.

        Returns
        -------
        str
            string 'host:port', where an IPv6 address is enclosed in square brackets, as in
            '[host]:port'

        See Also
        --------
        from_str : the inverse operation

        Examples
        --------
        >>> from mt.net import HostPort
        >>> HostPort.from_str("example.com:443").to_str()
        'example.com:443'
        >>> HostPort.from_str("[::1]:80").to_str()
        '[0000:0000:0000:0000:0000:0000:0000:0001]:80'
        """
        host, port = self.socket_address()
        if self.host_addr is None:
            return f"{host}:{port}"
        if self.is_v6():
            return f"[{host}]:{port}"
        return f"{host}:{port}"

    @classmethod
    def from_str(cls, s: str):
        """Deserializes from a string.

        Parameters
        ----------
        s : str
            string of the form 'host:port'. The host can be an IPv4 address, an IPv6 address
            (optionally
            in square brackets), a host name or a fully qualified domain name. It can also be empty
            or '*', meaning all interfaces, as in ':30443'.

        Returns
        -------
        HostPort
            the parsed instance. A host made of digits and dots is parsed as an IPv4 address and a
            host
            containing a colon as an IPv6 address. Otherwise it is kept as the host name.

        Raises
        ------
        ValueError
            if the port is missing or invalid, or if the address cannot be parsed

        See Also
        --------
        to_str : the inverse operation

        Examples
        --------
        >>> from mt.net import HostPort
        >>> hp = HostPort.from_str("192.168.1.5:443")
        >>> hp.host_addr, hp.host_name, hp.port
        (IPv4Address('192.168.1.5'), None, 443)
        >>> hp = HostPort.from_str("example.com:443")
        >>> hp.host_addr, hp.host_name, hp.port
        (None, 'example.com', 443)
        >>> hp = HostPort.from_str("[::1]:80")
        >>> hp.host_addr, hp.is_v6()
        (IPv6Address('::1'), True)
        >>> HostPort.from_str("*:30443").host_name
        ''
        >>> HostPort.from_str("nocolon")
        Traceback (most recent call last):
            ...
        ValueError: Port not found in input: 'nocolon'
        """
        i = s.rfind(":")
        if i < 0:
            raise ValueError(f"Port not found in input: '{s}'")
        port = int(s[i + 1 :])
        host = s[:i]

        if ":" in host:  # must be ipv6
            if host[0] == "[" and host[-1] == "]":
                host = host[1:-1]
            return HostPort(port, host_addr=ipaddress.IPv6Address(host))

        if len(host) == 0 or host == "*":
            return HostPort(port, host_name="")

        if not "." in host:
            return HostPort(port, host_name=host)

        if re.search("[^0-9.]", host) is None:  # ipv4
            return HostPort(port, host_addr=ipaddress.IPv4Address(host))

        return HostPort(port, host_name=host)


def listen_to_port(
    listen_config: str,
    blocking: bool = True,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
) -> socket.socket:
    """Listens to a local port, returning the listening socket.

    The function repeats indefinitely until it can open the port, waiting 5 seconds between
    attempts,
    for example if the port is in use. It returns early only if the config cannot be parsed. Address
    reuse is enabled (`SO_REUSEADDR`) and the backlog is 5.

    Parameters
    ----------
    listen_config : str
        listening config as an 'addr:port' pair, see :func:`HostPort.from_str`. For example,
        ':30443', '0.0.0.0:324', 'localhost:345', etc.
    blocking : bool, optional
        whether or not the returning socket is blocking. Default is True.
    logger : mt.logg.IndentedLoggerAdapter, optional
        logger for debugging purposes

    Returns
    -------
    dock_socket : socket.socket or None
        the output listening socket. None is returned if the listening config cannot be parsed. The
        caller is responsible for closing the socket.

    Examples
    --------
    >>> from mt.net import listen_to_port
    >>> sock = listen_to_port("127.0.0.1:0")  # port 0 asks the OS for a free port
    >>> sock.getsockname()[0]
    '127.0.0.1'
    >>> sock.close()
    """

    while True:
        try:
            listen_hostport = HostPort.from_str(listen_config)
            listen_address = listen_hostport.socket_address()
        except ValueError:
            if logger:
                logger.warn_last_exception()
                logger.error(
                    f"Unable to parse listening config: '{listen_config}'"
                )
            return

        try:
            family = socket.AF_INET6 if listen_hostport.is_v6() else socket.AF_INET
            socket_type = socket.SOCK_STREAM
            if not blocking:
                socket_type |= socket.SOCK_NONBLOCK
            dock_socket = socket.socket(family, socket_type)
        except OSError:
            if logger:
                logger.warn_last_exception()
            sleep(5)
            continue

        try:
            dock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            dock_socket.bind(listen_address)
            dock_socket.listen(5)
            break
        except OSError as e:
            if logger:
                if e.errno == 98:
                    logger.warn(
                        f"Unable to bind to local port {listen_address} which is in use. "
                        "Please wait until it is available."
                    )
                else:
                    logger.warn_last_exception()
            dock_socket.close()
            sleep(5)

    if logger:
        logger.info(f"Listening at '{listen_config}'.")

    return dock_socket
