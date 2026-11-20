"""Tests for bin/unifi, run against a local HTTPS server with a self-signed certificate."""

import argparse
import hashlib
import http.server
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from typing import cast
from unittest import mock

from tests.helpers import BIN, load_script

UNIFI = os.path.join(BIN, "unifi")
API = "/proxy/network/integration/v1"
KEY = "test-api-key"
DEVICES = [{"id": f"d{i}", "name": f"device-{i}"} for i in range(5)]
WRONG_PIN = "00" * 32


def page(records, query, max_page=200):
    offset = int(query.get("offset", ["0"])[0])
    limit = min(int(query.get("limit", ["200"])[0]), max_page)
    data = records[offset : offset + limit]
    return {
        "offset": offset,
        "limit": limit,
        "count": len(data),
        "totalCount": len(records),
        "data": data,
    }


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        cast(ConsoleServer, self.server).requests.append((self.path, self.headers.get("X-API-KEY")))
        if self.headers.get("X-API-KEY") != KEY:
            self.reply(401, {"error": "unauthorized"})
            return
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path == f"{API}/info":
            self.reply(200, {"applicationVersion": "9.9.9"})
        elif url.path == f"{API}/sites":
            self.reply(200, page([{"id": "site-1", "name": "Default"}], query))
        elif url.path == f"{API}/sites/site-1/devices":
            # Pages of two force the client to follow pagination.
            self.reply(200, page(DEVICES, query, max_page=2))
        else:
            self.reply(404, {})

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ConsoleServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, cert, key):
        super().__init__(("127.0.0.1", 0), Handler)
        self.requests = []
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        self.socket = context.wrap_socket(self.socket, server_side=True)

    def handle_error(self, request, client_address):
        pass


@unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a test certificate")
class UnifiCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certs = tempfile.mkdtemp()
        cert = os.path.join(cls.certs, "cert.pem")
        key = os.path.join(cls.certs, "key.pem")
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", key, "-out", cert, "-days", "1", "-subj", "/CN=console.invalid",
            ],
            check=True,
            capture_output=True,
        )
        with open(cert, encoding="ascii") as handle:
            der = ssl.PEM_cert_to_DER_cert(handle.read())
        cls.pin = hashlib.sha256(der).hexdigest()
        cls.pin_colons = ":".join(cls.pin[i : i + 2] for i in range(0, 64, 2)).upper()
        cls.server = ConsoleServer(cert, key)
        cls.port = str(cls.server.server_address[1])
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.certs)

    def setUp(self):
        self.server.requests.clear()
        self.config_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.config_home)

    def run_unifi(self, *args, env=None):
        base = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": self.config_home,
            "XDG_CONFIG_HOME": self.config_home,
            "UNIFI_API_KEY": KEY,
        }
        base.update(env or {})
        base = {name: value for name, value in base.items() if value is not None}
        return subprocess.run(
            [sys.executable, UNIFI, *args],
            env=base,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def console(self, *args):
        return ["--host", "127.0.0.1", "--port", self.port, *args]

    def config(self):
        with open(os.path.join(self.config_home, "unifi", "config.json"), encoding="utf-8") as handle:
            return handle.read()

    def test_pinned_certificate_is_accepted(self):
        result = self.run_unifi("info", *self.console("--cert-sha256", self.pin))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"applicationVersion": "9.9.9"})
        self.assertEqual(self.server.requests, [(f"{API}/info", KEY)])

    def test_pin_accepts_openssl_fingerprint_line(self):
        result = self.run_unifi(
            "info", *self.console("--cert-sha256", f"sha256 Fingerprint={self.pin_colons}")
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pin_from_environment(self):
        result = self.run_unifi("info", *self.console(), env={"UNIFI_CERT_SHA256": self.pin_colons})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_pin_sends_no_request(self):
        result = self.run_unifi("info", *self.console("--cert-sha256", WRONG_PIN))
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match the pinned fingerprint", result.stderr)
        self.assertIn(self.pin_colons, result.stderr)
        self.assertEqual(self.server.requests, [])

    def test_self_signed_certificate_fails_without_pin(self):
        result = self.run_unifi("info", *self.console())
        self.assertEqual(result.returncode, 1)
        self.assertIn("TLS certificate verification failed", result.stderr)
        self.assertEqual(self.server.requests, [])

    def test_cert_fingerprint_needs_no_key_and_sends_no_request(self):
        result = self.run_unifi("cert-fingerprint", *self.console(), env={"UNIFI_API_KEY": None})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), self.pin_colons)
        self.assertEqual(self.server.requests, [])

    def test_paged_list_is_followed_to_the_end(self):
        result = self.run_unifi(
            "devices", *self.console("--site", "site-1", "--cert-sha256", self.pin)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([d["id"] for d in json.loads(result.stdout)], [d["id"] for d in DEVICES])
        self.assertEqual(len(self.server.requests), 3)

    def test_rejected_key_reports_401(self):
        result = self.run_unifi(
            "info", *self.console("--cert-sha256", self.pin), env={"UNIFI_API_KEY": "wrong"}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("API key rejected", result.stderr)

    def test_setup_saves_host_site_and_pin_but_no_key(self):
        result = self.run_unifi("setup", *self.console("--cert-sha256", self.pin_colons))
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = self.config()
        self.assertEqual(
            json.loads(saved),
            {"host": "127.0.0.1", "site": "site-1", "cert_sha256": self.pin},
        )
        self.assertNotIn(KEY, saved)

    def test_setup_for_another_host_drops_old_site_and_pin(self):
        os.makedirs(os.path.join(self.config_home, "unifi"))
        with open(os.path.join(self.config_home, "unifi", "config.json"), "w", encoding="utf-8") as handle:
            json.dump({"host": "old.invalid", "site": "old-site", "cert_sha256": WRONG_PIN}, handle)
        # Without a pin the self-signed server fails verification, after the
        # host has already been saved.
        result = self.run_unifi("setup", *self.console())
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(self.config()), {"host": "127.0.0.1"})


class UnifiModuleTest(unittest.TestCase):
    def setUp(self):
        self.unifi = load_script("unifi")
        self.config_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.config_home)
        config_dir = os.path.join(self.config_home, "unifi")
        for name, value in (
            ("CONFIG_DIR", config_dir),
            ("CONFIG_PATH", os.path.join(config_dir, "config.json")),
        ):
            patcher = mock.patch.object(self.unifi, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def no_keychain(self):
        return mock.patch.object(self.unifi, "keychain_available", return_value=False)

    def test_normalize_fingerprint_forms(self):
        pin = "ab" * 32
        colons = ":".join(["AB"] * 32)
        for raw in (pin, pin.upper(), colons, f"SHA256 Fingerprint={colons}", f"  {colons}\n"):
            self.assertEqual(self.unifi.normalize_fingerprint(raw), pin)

    def test_normalize_fingerprint_rejects_other_input(self):
        for raw in ("ab" * 31, "zz" * 32, "sha1 Fingerprint=" + "ab" * 20):
            with self.assertRaises(self.unifi.UnifiError):
                self.unifi.normalize_fingerprint(raw)

    def test_without_keychain_the_key_must_come_from_the_environment(self):
        with self.no_keychain(), mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(self.unifi.subprocess, "run", side_effect=AssertionError):
            with self.assertRaises(self.unifi.UnifiError) as caught:
                self.unifi.get_api_key("console.invalid")
        self.assertIn("UNIFI_API_KEY", str(caught.exception))
        self.assertNotIn("Keychain", str(caught.exception))

    def test_setup_without_keychain_or_key_stops_before_prompting(self):
        args = argparse.Namespace(host="console.invalid", cert_sha256=None)
        stdin = mock.Mock(**{"isatty.return_value": False, "read.side_effect": AssertionError})
        with self.no_keychain(), mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(self.unifi.sys, "stdin", stdin), \
                mock.patch.object(self.unifi.getpass, "getpass", side_effect=AssertionError):
            with self.assertRaises(self.unifi.UnifiError) as caught:
                self.unifi.cmd_setup(args)
        self.assertIn("UNIFI_API_KEY", str(caught.exception))
        self.assertFalse(os.path.exists(self.unifi.CONFIG_PATH))


if __name__ == "__main__":
    unittest.main()
