"""Tests for bin/unifi-ssh and the askpass helper, with a fake ssh on PATH."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from tests.helpers import BIN, LIBEXEC, load_script

UNIFI_SSH = os.path.join(BIN, "unifi-ssh")
ASKPASS = os.path.join(LIBEXEC, "unifi-askpass")
ASKPASS_ANSWER = "example-askpass-answer"

# Prints what it was given and the askpass answer, or fails the way a console
# with the wrong password does, depending on FAKE_SSH_MODE.
FAKE_SSH = textwrap.dedent(
    """\
    import os, subprocess, sys
    if os.environ.get("FAKE_SSH_MODE") == "denied":
        sys.stderr.write("root@console: Permission denied (keyboard-interactive).\\n")
        sys.exit(255)
    answer = subprocess.run(
        [os.environ["SSH_ASKPASS"], "root@console's password: "],
        capture_output=True, text=True,
    ).stdout
    print("argv=" + "|".join(sys.argv[1:]))
    print("require=" + os.environ.get("SSH_ASKPASS_REQUIRE", ""))
    print("password=" + answer)
    """
)


class UnifiSshTest(unittest.TestCase):
    def setUp(self):
        self.unifi_ssh = load_script("unifi-ssh")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        fake_bin = os.path.join(self.tmp, "bin")
        os.mkdir(fake_bin)
        self.fake_ssh = os.path.join(fake_bin, "ssh")
        with open(self.fake_ssh, "w", encoding="utf-8") as handle:
            handle.write(f"#!{sys.executable}\n{FAKE_SSH}")
        os.chmod(self.fake_ssh, 0o755)
        self.path = fake_bin + os.pathsep + os.environ.get("PATH", "")

    def run_ssh(self, *args, env=None):
        base = {
            "PATH": self.path,
            "HOME": self.tmp,
            "XDG_CONFIG_HOME": self.tmp,
        }
        base.update(env or {})
        return subprocess.run(
            [sys.executable, UNIFI_SSH, *args],
            env=base,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_askpass_helper_lives_in_libexec(self):
        self.assertEqual(self.unifi_ssh.ASKPASS, os.path.realpath(ASKPASS))
        self.assertTrue(os.access(ASKPASS, os.X_OK))

    def test_checks_carry_no_fixed_ipv4_addresses(self):
        ipv4 = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        for name, check in self.unifi_ssh.CHECKS.items():
            command = check.get("shell") or " ".join(check.get("argv", []))
            self.assertIsNone(ipv4.search(command), name)

    def test_rtsp_sessions_count_the_original_destination(self):
        result = self.run_ssh("run", "--check", "protect-rtsp-sessions", "--host", "console", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("conntrack -L -p tcp --dport 554 --state ESTABLISHED", result.stdout)

    def test_sensitive_check_needs_confirm(self):
        result = self.run_ssh("run", "--check", "mca-dump", "--host", "console", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--confirm", result.stderr)

    def test_tcpdump_needs_interface_and_bounded_count(self):
        base = ["run", "--check", "tcpdump", "--host", "console", "--dry-run", "--confirm"]
        self.assertIn("--iface", self.run_ssh(*base).stderr)
        self.assertIn("--count", self.run_ssh(*base, "--iface", "eth0", "--count", "501").stderr)
        result = self.run_ssh(*base, "--iface", "eth0", "--filter", "port 53")
        self.assertEqual(result.stdout.strip(), "tcpdump -n -l -c 50 -i eth0 port 53")

    def test_ubv_timing_validates_mac(self):
        result = self.run_ssh("run", "--check", "ubv-timing", "--host", "console", "--mac", "xyz", "--dry-run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--mac", result.stderr)

    def test_missing_password_stops_before_ssh(self):
        result = self.run_ssh("run", "--check", "uptime", "--host", "console")
        self.assertEqual(result.returncode, 1)
        self.assertIn("UNIFI_SSH_PASSWORD is not set", result.stderr)
        self.assertNotIn("argv=", result.stdout)

    def test_password_reaches_ssh_through_askpass(self):
        result = self.run_ssh(
            "run", "--check", "uptime", "--host", "console", env={"UNIFI_SSH_PASSWORD": ASKPASS_ANSWER}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("argv=-o|ConnectTimeout=10|console|uptime", result.stdout)
        self.assertIn("require=force", result.stdout)
        self.assertIn(f"password={ASKPASS_ANSWER}", result.stdout)

    def test_rejected_password_names_the_variable(self):
        result = self.run_ssh(
            "run", "--check", "uptime", "--host", "console",
            env={"UNIFI_SSH_PASSWORD": ASKPASS_ANSWER, "FAKE_SSH_MODE": "denied"},
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("UNIFI_SSH_PASSWORD", result.stderr)

    def test_askpass_refuses_host_key_prompt(self):
        result = subprocess.run(
            [ASKPASS, "Are you sure you want to continue connecting (yes/no/[fingerprint])? "],
            env={"PATH": os.environ.get("PATH", ""), "UNIFI_SSH_PASSWORD": ASKPASS_ANSWER},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
