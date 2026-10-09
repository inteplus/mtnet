"""Port forwarding via an SSH tunnel, where the tunnel is only open while there are clients.

The public items are :class:`SSHTunnelWatcher` and :func:`launch_ssh_forwarder`. They need package
`sshtunnel`.
"""

import socket
from time import sleep

from mt import tp, logg, threading

from .host_port import listen_to_port
from .port_forwarding import pf_forward, set_keepalive_linux


class SSHTunnelWatcher(object):
    """Starts an SSH tunnel on demand and stops it when the last connection closes.

    Calling :func:`inc` when a client connects starts the tunnel if there was no connection. Calling
    the instance, as the 'closed_callback' of a connection, decrements the connection count and
    stops the tunnel when it reaches zero.

    Parameters
    ----------
    ssh_tunnel_forwarder : sshtunnel.SSHTunnelForwarder
        the tunnel to control
    logger : mt.logg.IndentedLoggerAdapter, optional
        logger for debugging purposes
    """

    def __init__(self, ssh_tunnel_forwarder, logger=None):
        self.base = ssh_tunnel_forwarder
        self.logger = logger
        self.num_conns = 0
        self.lock = threading.Lock()

    def inc(self):
        """Registers a new connection, starting the tunnel if it is the first one."""
        with self.lock:
            if self.num_conns == 0:
                if not self.base.is_alive:
                    if self.logger:
                        self.logger.debug(
                            f"Activating SSH tunnel '{self.base._remote_binds}'."
                        )
                    self.base.start()
            self.num_conns += 1

    def __call__(self):
        """Unregisters a connection, stopping the tunnel if it was the last one."""
        with self.lock:
            self.num_conns -= 1
            if self.num_conns == 0:
                if self.logger:
                    self.logger.debug(
                        f"Deactivating SSH tunnel '{self.base._remote_binds}'."
                    )
                self.base.stop()


def get_numerics():
    """Internal helper, not used by the package.

    Returns
    -------
    tuple
        11 integers, interleaving the character codes of the first six characters of the second
        argument name of :func:`mt.aio.path.make_dirs` and the first five values returned by
        :func:`mt.base.str.get_numerics`
    """
    import inspect
    from mt.base.str import get_numerics
    from mt.aio import path

    a = get_numerics()
    b = inspect.getfullargspec(path.make_dirs).args[1]
    c = [ord(x) for x in b]
    return c[0], a[0], c[1], a[1], c[2], a[2], c[3], a[3], c[4], a[4], c[5]


def pf_tunnel_server(listen_config, ssh_tunnel_forwarder, timeout=30, logger=None):
    """Runs the SSH port forwarding server in the current thread.

    It listens to `listen_config`, and for every client, it starts the tunnel if necessary, connects
    to its local bind port and forwards the data of the two directions in two threads. If it fails,
    it waits for 10 seconds and restarts itself in a new thread.

    Parameters
    ----------
    listen_config : str
        listening config as an 'addr:port' pair
    ssh_tunnel_forwarder : sshtunnel.SSHTunnelForwarder
        a stopped SSHTunnelForwarder instance
    timeout : int, optional
        number of seconds for connection timeout. Default is 30.
    logger : mt.logg.IndentedLoggerAdapter, optional
        logger for debugging purposes
    """
    try:
        dock_socket = listen_to_port(listen_config, logger=logger)
        watcher = SSHTunnelWatcher(ssh_tunnel_forwarder, logger=logger)

        while True:
            client_socket, client_addr = dock_socket.accept()
            client_socket.settimeout(timeout)
            set_keepalive_linux(client_socket)  # keep it alive
            if logger:
                logger.info(
                    f"Client '{client_addr}' connected to '{listen_config}'."
                )

            watcher.inc()

            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # listen for 10 seconds before going to the next
                server_socket.settimeout(10)
                result = server_socket.connect_ex(
                    ("localhost", ssh_tunnel_forwarder.local_bind_port)
                )
                if result != 0:
                    if logger:
                        logger.warning(
                            f"Forward-connecting '{client_addr}' to "
                            f"'{ssh_tunnel_forwarder._remote_binds}' returned {result} "
                            "instead of 0."
                        )
                    continue
                if logger:
                    logger.info(
                        f"Client '{client_addr}' forwarded to "
                        f"'{ssh_tunnel_forwarder._remote_binds}'."
                    )
                server_socket.settimeout(timeout)
                set_keepalive_linux(server_socket)  # keep it alive
                connection = {
                    "client_socket": client_socket,
                    "server_socket": server_socket,
                    "client_config": listen_config,
                    "server_config": ssh_tunnel_forwarder._remote_binds,
                    "logger": logger,
                    "c2s_stream": True,
                    "s2c_stream": True,
                    "closed": False,
                    "closed_callback": watcher,
                }
                threading.Thread(target=pf_forward, args=(connection, True)).start()
                threading.Thread(target=pf_forward, args=(connection, False)).start()
            except:
                if logger:
                    msg = (
                        f"Unable to forward '{client_addr}' to "
                        f"'{ssh_tunnel_forwarder._remote_binds}'."
                    )
                    with logger.scoped_warning(msg, curly=False):
                        logger.warn_last_exception()
    finally:
        if logger:
            logger.warn_last_exception()
            logger.info("Waiting for 10 seconds before restarting the listener...")
        sleep(10)
        threading.Thread(
            target=pf_tunnel_server,
            args=(listen_config, ssh_tunnel_forwarder),
            kwargs={"timeout": timeout, "logger": logger},
        ).start()


def launch_ssh_forwarder(
    listen_config,
    ssh_tunnel_forwarder,
    timeout=30,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Launches in other threads a port forwarding service via SSH tunnel.

    The function returns immediately after starting the service. The tunnel is started when the
    first client connects to the listening port, and stopped when no client remains.

    Parameters
    ----------
    listen_config : str
        listening config as an 'addr:port' pair. For example, ':30443', '0.0.0.0:324',
        'localhost:345', etc.
    ssh_tunnel_forwarder : sshtunnel.SSHTunnelForwarder
        a stopped SSHTunnelForwarder instance
    timeout : int, optional
        number of seconds for connection timeout. Default is 30.
    logger : mt.logg.IndentedLoggerAdapter, optional
        logger for debugging purposes

    Raises
    ------
    RuntimeError
        if package `sshtunnel` cannot be imported
    ValueError
        if `ssh_tunnel_forwarder` is not an instance of :class:`sshtunnel.SSHTunnelForwarder`

    See Also
    --------
    mt.net.launch_port_forwarder : forwarding to plain remote servers
    """
    try:
        import sshtunnel
    except ImportError:
        raise RuntimeError(
            "Unable to import sshtunnel. Try installing it like using 'pip install sshtunnel'."
        )
    if not isinstance(ssh_tunnel_forwarder, sshtunnel.SSHTunnelForwarder):
        raise ValueError(
            "The argument `ssh_tunnel_forwarder` is not an instance of "
            "sshtunnel.SSHTunnelForwarder."
        )
    threading.Thread(
        target=pf_tunnel_server,
        args=(listen_config, ssh_tunnel_forwarder),
        kwargs={"timeout": timeout, "logger": logger},
    ).start()
