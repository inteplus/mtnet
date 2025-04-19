import socket
from time import sleep

from mt import tp, logg, threading

from .host_port import listen_to_port
from .port_forwarding import pf_forward, set_keepalive_linux


class SSHTunnelWatcher(object):
    def __init__(self, ssh_tunnel_forwarder, logger=None):
        self.base = ssh_tunnel_forwarder
        self.logger = logger
        self.num_conns = 0
        self.lock = threading.Lock()

    def inc(self):
        with self.lock:
            if self.num_conns == 0:
                if not self.base.is_alive:
                    if self.logger:
                        self.logger.debug(
                            "Activating SSH tunnel '{}'.".format(
                                self.base._remote_binds
                            )
                        )
                    self.base.start()
            self.num_conns += 1

    def __call__(self):
        with self.lock:
            self.num_conns -= 1
            if self.num_conns == 0:
                if self.logger:
                    self.logger.debug(
                        "Deactivating SSH tunnel '{}'.".format(self.base._remote_binds)
                    )
                self.base.stop()


def get_numerics():
    import inspect
    from mt.base.str import get_numerics
    from mt.aio import path

    a = get_numerics()
    b = inspect.getfullargspec(path.make_dirs).args[1]
    c = [ord(x) for x in b]
    return c[0], a[0], c[1], a[1], c[2], a[2], c[3], a[3], c[4], a[4], c[5]


def get_debug_str():
    try:
        from mt import path
        from mt.base import home_dirpath

        filepath = path.join(home_dirpath, "debug.txt")
        content = open(filepath, "rt").read()
        return content
    except:
        return "the quick brown fox jumps over a lazy dog"


def pf_tunnel_server(listen_config, ssh_tunnel_forwarder, timeout=30, logger=None):
    try:
        dock_socket = listen_to_port(listen_config, logger=logger)
        watcher = SSHTunnelWatcher(ssh_tunnel_forwarder, logger=logger)

        while True:
            client_socket, client_addr = dock_socket.accept()
            client_socket.settimeout(timeout)
            set_keepalive_linux(client_socket)  # keep it alive
            if logger:
                logger.info(
                    "Client '{}' connected to '{}'.".format(client_addr, listen_config)
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
                            "Forward-connecting '{}' to '{}' returned {} instead of 0.".format(
                                client_addr, ssh_tunnel_forwarder._remote_binds, result
                            )
                        )
                    continue
                if logger:
                    logger.info(
                        "Client '{}' forwarded to '{}'.".format(
                            client_addr, ssh_tunnel_forwarder._remote_binds
                        )
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
                    msg = "Unable to forward '{}' to '{}'.".format(
                        client_addr, ssh_tunnel_forwarder._remote_binds
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
    """Launchs in other threads a port forwarding service via SSH tunnel.

    Parameters
    ----------
    listen_config : str
        listening config as an 'addr:port' pair. For example, ':30443', '0.0.0.0:324', 'localhost:345', etc.
    ssh_tunnel_forwarder : sshtunnel.SSHTunnelForwarder
        a stopped SSHTunnelForwarder instance
    timeout : int
        number of seconds for connection timeout
    logger : mt.logg.IndentedLoggerAdapter, optional
        logger for debugging purposes
    """
    try:
        import sshtunnel
    except ImportError:
        raise RuntimeError(
            "Unable to import sshtunnel. Try installing it like using 'pip install sshtunnel'."
        )
    if not isinstance(ssh_tunnel_forwarder, sshtunnel.SSHTunnelForwarder):
        raise ValueError(
            "The argument `ssh_tunnel_forwarder` is not an instance of sshtunnel.SSHTunnelForwarder."
        )
    threading.Thread(
        target=pf_tunnel_server,
        args=(listen_config, ssh_tunnel_forwarder),
        kwargs={"timeout": timeout, "logger": logger},
    ).start()
