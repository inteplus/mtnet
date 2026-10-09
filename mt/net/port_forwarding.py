"""Port forwarding with threads: listens to a local port and forwards every connection to one of
a list of remote servers.

The public function is :func:`launch_port_forwarder`. For an asynchronous version, see
:func:`mt.net.port_forwarder_actx`.
"""

import socket
from time import sleep

from mt import tp, logg, threading

from .host_port import HostPort, listen_to_port


def set_keepalive_linux(sock, after_idle_sec=1, interval_sec=3, max_fails=5):
    """Set TCP keepalive on an open socket.

    It activates after 1 second (after_idle_sec) of idleness,
    then sends a keepalive ping once every 3 seconds (interval_sec),
    and closes the connection after 5 failed ping (max_fails), or 15 seconds.

    Parameters
    ----------
    sock : socket.socket
        an open TCP socket
    after_idle_sec : int, optional
        seconds of idleness before the first keepalive probe. Default is 1.
    interval_sec : int, optional
        seconds between keepalive probes. Default is 3.
    max_fails : int, optional
        number of failed probes after which the connection is closed. Default is 5.
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)


def set_keepalive_osx(sock, after_idle_sec=1, interval_sec=3, max_fails=5):
    """Set TCP keepalive on an open socket, on macOS.

    It sends a keepalive ping once every `interval_sec` seconds (3 by default). The arguments
    `after_idle_sec` and `max_fails` are accepted for compatibility with :func:`set_keepalive_linux`
    but are ignored.

    Parameters
    ----------
    sock : socket.socket
        an open TCP socket
    after_idle_sec : int, optional
        ignored
    interval_sec : int, optional
        seconds between keepalive probes. Default is 3.
    max_fails : int, optional
        ignored
    """
    # scraped from /usr/include, not exported by python's socket module
    TCP_KEEPALIVE = 0x10
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, TCP_KEEPALIVE, interval_sec)


def pf_shutdown_socket(socket, mode, config=None, logger=None):
    """Shuts down a socket, logging instead of raising any error.

    Parameters
    ----------
    socket : socket.socket
        the socket to shut down
    mode : int
        one of `socket.SHUT_RD`, `socket.SHUT_WR` and `socket.SHUT_RDWR`
    config : str, optional
        description of the socket, for logging
    logger : mt.logg.IndentedLoggerAdapter, optional
        logger for debugging purposes

    Returns
    -------
    bool
        whether the shutdown succeeded
    """
    try:
        socket.shutdown(mode)
        return True
    except:
        if logger:
            msg = f"Shuting down socket '{config}' with mode {mode}"
            with logger.scoped_warning(msg, curly=False):
                logger.warn_last_exception()
        return False


def pf_shutdown_stream(connection, is_c2s):
    """Shuts down the client->server stream or the server->client stream.

    If both streams of the connection are down, the connection is marked as closed and its optional
    'closed_callback' is invoked.

    Parameters
    ----------
    connection : dict
        the connection state, with keys 'client_socket', 'server_socket', 'client_config',
        'server_config', 'logger', 'c2s_stream', 's2c_stream', 'closed' and optionally
        'closed_callback'
    is_c2s : bool
        True for the client->server stream, False for the server->client stream
    """
    logger = connection["logger"]
    if is_c2s:
        if connection["c2s_stream"]:
            connection["c2s_stream"] = False
            with logg.scoped_debug(
                f"Shutting down stream client {connection['client_config']} "
                f"-> server {connection['server_config']}",
                logger=logger,
                curly=False,
            ):
                pf_shutdown_socket(
                    connection["client_socket"],
                    socket.SHUT_RD,
                    config=connection["client_config"],
                    logger=logger,
                )
                pf_shutdown_socket(
                    connection["server_socket"],
                    socket.SHUT_WR,
                    config=connection["server_config"],
                    logger=logger,
                )
    else:
        if connection["s2c_stream"]:
            connection["s2c_stream"] = False
            with logg.scoped_debug(
                f"Shutting down stream server {connection['server_config']} "
                f"-> client {connection['client_config']}",
                logger=logger,
                curly=False,
            ):
                pf_shutdown_socket(
                    connection["server_socket"],
                    socket.SHUT_RD,
                    config=connection["server_config"],
                    logger=logger,
                )
                pf_shutdown_socket(
                    connection["client_socket"],
                    socket.SHUT_WR,
                    config=connection["client_config"],
                    logger=logger,
                )

    if (
        connection["c2s_stream"] is False
        and connection["s2c_stream"] is False
        and not connection["closed"]
    ):
        connection["closed"] = True
        if "closed_callback" in connection:
            connection["closed_callback"]()


def pf_forward(connection, is_c2s):
    """Forwards data in one direction of a connection until the stream ends.

    It is meant to run in a thread. Data is read from the source socket in chunks of 1024 bytes and
    sent to the destination socket. On end of stream, timeout or error, the stream (and on error,
    also the opposite one) is shut down with :func:`pf_shutdown_stream`.

    Parameters
    ----------
    connection : dict
        the connection state, see :func:`pf_shutdown_stream`
    is_c2s : bool
        True to forward from the client to the server, False for the opposite direction
    """
    if is_c2s:
        src_socket = connection["client_socket"]
        dst_socket = connection["server_socket"]
    else:
        src_socket = connection["server_socket"]
        dst_socket = connection["client_socket"]
    logger = connection["logger"]

    string = " "
    while string:
        try:
            string = src_socket.recv(1024)
        except socket.timeout:
            if logger:
                if is_c2s:
                    msg = (
                        f"Stream client '{connection['client_config']}' "
                        f"-> server '{connection['server_config']}' has timed out"
                    )
                else:
                    msg = (
                        f"Stream server '{connection['client_config']}' "
                        f"-> client '{connection['server_config']}' has timed out"
                    )
                with logger.scoped_warning(msg, curly=False):
                    logger.warn_last_exception()

                pf_shutdown_stream(connection, is_c2s)
            break
        except OSError:
            if logger:
                msg = (
                    f"Broken connection client '{connection['client_config']}' "
                    f"<-> server '{connection['server_config']}'  because"
                )
                with logger.scoped_warning(msg, curly=False):
                    logger.warn_last_exception()
            pf_shutdown_stream(connection, is_c2s)
            pf_shutdown_stream(connection, not is_c2s)
            break

        if string:
            dst_socket.sendall(string)
        else:
            pf_shutdown_stream(connection, is_c2s)


def pf_server(listen_config, connect_configs, timeout=30, logger=None):
    """Runs the port forwarding server in the current thread.

    It listens to `listen_config`, and for every client, it connects to the first working server in
    `connect_configs`, then starts two threads to forward the data of the two directions. If it
    fails,
    it waits for 10 seconds and restarts itself in a new thread (with the default timeout).

    Parameters
    ----------
    listen_config : str
        listening config as an 'addr:port' pair
    connect_configs : iterable
        list of connecting configs, each of which is an 'addr:port' pair
    timeout : int, optional
        number of seconds for connection timeout. Default is 30.
    logger : mt.logg.IndentedLoggerAdapter, optional
        logger for debugging purposes
    """
    try:
        dock_socket = listen_to_port(listen_config, logger=logger)

        while True:
            client_socket, client_addr = dock_socket.accept()
            client_socket.settimeout(timeout)
            set_keepalive_linux(client_socket)  # keep it alive
            if logger:
                logger.info(
                    f"Client '{client_addr}' connected to '{listen_config}'."
                )

            for connect_config in connect_configs:
                try:
                    connect_hostport = HostPort.from_str(connect_config)
                    connect_address = connect_hostport.socket_address()
                except ValueError:
                    if logger:
                        logger.warn_last_exception()
                        logger.error(
                            f"Unable to parse connecting config: '{connect_config}'"
                        )
                    break

                try:
                    family = (
                        socket.AF_INET6 if connect_hostport.is_v6() else socket.AF_INET
                    )
                    server_socket = socket.socket(family, socket.SOCK_STREAM)
                    # listen for 10 seconds before going to the next
                    server_socket.settimeout(10)
                    result = server_socket.connect_ex(connect_address)
                    if result != 0:
                        if logger:
                            logger.warning(
                                f"Forward-connecting '{client_addr}' to '{connect_config}' "
                                f"returned {result} instead of 0."
                            )
                        continue
                    if logger:
                        logger.info(
                            f"Client '{client_addr}' forwarded to '{connect_config}'."
                        )
                    server_socket.settimeout(timeout)
                    set_keepalive_linux(server_socket)  # keep it alive
                    connection = {
                        "client_socket": client_socket,
                        "server_socket": server_socket,
                        "client_config": listen_config,
                        "server_config": connect_config,
                        "logger": logger,
                        "c2s_stream": True,
                        "s2c_stream": True,
                        "closed": False,
                    }
                    threading.Thread(target=pf_forward, args=(connection, True)).start()
                    threading.Thread(
                        target=pf_forward, args=(connection, False)
                    ).start()

                    # wait for 1 sec to see if server disconnects disruptedly or not
                    sleep(1)
                    if connection["closed"]:  # already closed after 1 second?
                        if logger:
                            logger.warning(
                                "Connectioned terminated too quickly. Trying the next..."
                            )
                        continue  # bad config, try another one

                    break
                except:
                    if logger:
                        logger.warn_last_exception()
                        logger.warning(
                            f"Unable to forward '{client_addr}' to '{connect_config}'. "
                            "Skipping to next server."
                        )
                    continue
            else:
                if logger:
                    logger.error(
                        f"Unable to forward to any server for client '{client_addr}' "
                        f"connected to '{listen_config}'."
                    )
    finally:
        if logger:
            logger.info("Waiting for 10 seconds before restarting the listener...")
        sleep(10)
        threading.Thread(
            target=pf_server,
            args=(listen_config, connect_configs),
            kwargs={"logger": logger},
        ).start()


def launch_port_forwarder(
    listen_config,
    connect_configs,
    timeout=30,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Launches in other threads a port forwarding service.

    The function returns immediately after starting the service. For every client that connects to
    the listening port, the service tries the connecting configs in order and forwards the client to
    the first one that accepts the connection and stays connected for at least a second.

    Parameters
    ----------
    listen_config : str
        listening config as an 'addr:port' pair. For example, ':30443', '0.0.0.0:324',
        'localhost:345', etc.
    connect_configs : iterable
        list of connecting configs, each of which is an 'addr:port' pair. For example,
        'home2.sdfamily.co.uk:443', etc. Special case '::1:port' stands for localhost in ipv6 with
        a specific port.
    timeout : int, optional
        number of seconds for connection timeout. Default is 30.
    logger : mt.logg.IndentedLoggerAdapter, optional
        logger for debugging purposes

    See Also
    --------
    mt.net.port_forwarder_actx : asynchronous version
    mt.net.launch_ssh_forwarder : forwarding via an SSH tunnel
    """
    threading.Thread(
        target=pf_server,
        args=(listen_config, connect_configs),
        kwargs={"timeout": timeout, "logger": logger},
    ).start()
