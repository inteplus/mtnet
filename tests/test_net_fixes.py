"""Regression tests for mt.net.base, mt.net.port_forwarding and mt.net.port_forwarding_async."""

import asyncio
import socket
import unittest
from unittest import mock

import mt.net
from mt.net import base, port_forwarding, port_forwarding_async


def _closed_loopback_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestRepoSource(unittest.TestCase):
    def test_source_is_repo(self):
        self.assertTrue(mt.net.__file__.startswith("/home/minhtri/gitcentre/mtnet/"))


class TestGetDefaultIfaces(unittest.TestCase):
    def _run(self, addr_item):
        gws = {"default": {2: ("192.168.1.1", "eth0")}}
        with mock.patch.object(base.netifaces, "gateways", return_value=gws), mock.patch.object(
            base.netifaces, "ifaddresses", return_value={2: [addr_item]}
        ):
            return base.get_default_ifaces()

    def test_normal(self):
        res = self._run(
            {"addr": "192.168.1.5", "netmask": "255.255.255.0", "broadcast": "192.168.1.255"}
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(str(res[0][2]), "192.168.1.255")
        self.assertEqual(res[0][4], "eth0")

    def test_missing_broadcast_is_skipped(self):
        res = self._run({"addr": "192.168.1.5", "netmask": "255.255.255.0"})
        self.assertEqual(res, [])


class TestPfServerRestart(unittest.TestCase):
    def test_restart_passes_timeout(self):
        with mock.patch.object(port_forwarding, "sleep") as m_sleep, mock.patch.object(
            port_forwarding.threading, "Thread"
        ) as m_thread:
            # a failing listener (invalid config) triggers the restart in the finally block
            with mock.patch.object(
                port_forwarding, "listen_to_port", side_effect=OSError("boom")
            ):
                with self.assertRaises(OSError):
                    port_forwarding.pf_server("127.0.0.1:1", ["127.0.0.1:2"], timeout=7)
        m_sleep.assert_called_once_with(10)
        kwargs = m_thread.call_args.kwargs
        self.assertEqual(kwargs["kwargs"]["timeout"], 7)
        self.assertIs(kwargs["target"], port_forwarding.pf_server)


class TestScanRemotesRetryDelay(unittest.IsolatedAsyncioTestCase):
    async def test_sleep_matches_log(self):
        port = _closed_loopback_port()
        logger = mock.MagicMock()
        fwd = port_forwarding_async.PortForwardingService(
            "127.0.0.1:0", [f"127.0.0.1:{port}"], logger=logger
        )
        sleeps = []

        async def fake_sleep(t, *args, **kwargs):
            sleeps.append(t)

        with mock.patch.object(port_forwarding_async.asyncio, "sleep", fake_sleep):
            with self.assertRaises(ConnectionAbortedError):
                await fwd.scan_remotes()
        self.assertEqual(sleeps, [60, 600, 3600])
        msgs = [c.args[0] for c in logger.error.call_args_list]
        for t in (60, 600, 3600):
            self.assertIn(f"Will retry in {t} seconds.", msgs)

    async def test_no_logger_sleeps_60(self):
        port = _closed_loopback_port()
        fwd = port_forwarding_async.PortForwardingService("127.0.0.1:0", [f"127.0.0.1:{port}"])
        sleeps = []

        async def fake_sleep(t, *args, **kwargs):
            sleeps.append(t)
            if len(sleeps) >= 2:
                raise asyncio.CancelledError()

        with mock.patch.object(port_forwarding_async.asyncio, "sleep", fake_sleep):
            with self.assertRaises(asyncio.CancelledError):
                await fwd.scan_remotes()
        self.assertEqual(sleeps, [60, 60])


if __name__ == "__main__":
    unittest.main()
