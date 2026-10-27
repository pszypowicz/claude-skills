"""Tests for the ADO client library and ado-exec.sh, with fake curl and az.

Every test runs once per bash found on the machine, so macOS also covers
/bin/bash 3.2.
"""

import base64
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest
from typing import TYPE_CHECKING

TESTS = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(TESTS)
SCRIPTS = os.path.join(PLUGIN, "skills", "ado", "scripts")
LIB = os.path.join(SCRIPTS, "lib", "ado-client.sh")
FAKES = os.path.join(TESTS, "fakes.py")

ORG = "https://dev.azure.com/example-org"
PROJECT = "example-project"
ORG_TENANT = "11111111-2222-3333-4444-555555555555"
HOME_TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
NIL_TENANT = "00000000-0000-0000-0000-000000000000"
RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"
PAT = "examplepat0123456789"
PAT_BASIC = "Basic " + base64.b64encode(b":" + PAT.encode()).decode()

API = "ado_require_env; ado_resolve_auth; ado_api GET projects"
API_URL = "/%s/_apis/projects" % PROJECT
SIGNIN = "https://signin.example.invalid/_signin?realm=dev.azure.com"
MATERIALIZED = json.dumps({
    "message": "TF400813: Identity 'x' has not been materialized, "
               "please use interactive login over the browser first.",
    "typeKey": "AadUserStateException",
})
DUMP_ENV = [
    "python3", "-c",
    "import json, os; print(json.dumps({k: os.environ.get(k) for k in "
    "['ADO_ORG', 'ADO_TOKEN', 'AZURE_DEVOPS_EXT_PAT', 'ADO_AUTH_HEADER', 'ADO_TOKEN_MINTED']}))",
]


def jwt(tid, name="token", exp=None):
    def seg(obj):
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    claims = {"tid": tid, "name": name}
    if exp is not None:
        claims["exp"] = exp
    return "%s.%s.c2lnbmF0dXJl" % (seg({"alg": "RS256", "typ": "JWT"}), seg(claims))


def ok(body='{"value": []}', **extra):
    return dict({"status": 200, "body": body}, **extra)


def status(code, body="", content_type="application/json; charset=utf-8", **extra):
    return dict({"status": code, "body": body, "content_type": content_type}, **extra)


SIGNIN_REDIRECT = status(302, "<html>Object moved</html>", "text/html; charset=utf-8", location=SIGNIN)


# The groups below run once per shell through generated TestCase subclasses,
# so they must not be TestCases themselves.
_Base = unittest.TestCase if TYPE_CHECKING else object


class Fixture(_Base):
    SHELL = None

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ado-client-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        for tool in ("curl", "az"):
            self.install(tool)
        home = os.path.join(self.tmp, "home")
        os.mkdir(home)
        self.scenario = {"curl": [], "az": []}
        self.env = {
            "PATH": self.bin + os.pathsep + os.environ.get("PATH", ""),
            "HOME": home,
            "TMPDIR": self.tmp,
            "LANG": "C",
            "FAKE_DIR": self.tmp,
            "ADO_ORG": ORG,
            "ADO_PROJECT": PROJECT,
        }

    # -- fakes ---------------------------------------------------------------

    def install(self, tool):
        path = os.path.join(self.bin, tool)
        with open(path, "w") as f:
            f.write('#!/bin/sh\nexec python3 %s %s "$@"\n' % (shlex.quote(FAKES), tool))
        os.chmod(path, 0o755)

    def uninstall(self, tool):
        os.remove(os.path.join(self.bin, tool))

    def route_curl(self, url_contains, *responses):
        self.scenario["curl"].append({"url_contains": url_contains, "responses": list(responses)})

    def route_az(self, match, *responses):
        self.scenario["az"].append({"match": match, "responses": list(responses)})

    def org_tenant(self, value=ORG_TENANT, name="X-VSS-ResourceTenant", org=ORG):
        self.route_curl(org + "/_apis/connectionData",
                        dict(SIGNIN_REDIRECT, headers=[[name, value]]))

    def mint(self, *tokens):
        self.route_az(["account", "get-access-token"], *[{"stdout": t + "\n"} for t in tokens])

    def mint_fails(self, stderr):
        self.route_az(["account", "get-access-token"], {"stderr": stderr, "exit": 1})

    def api(self, *responses):
        self.route_curl(API_URL, *responses)

    # -- running -------------------------------------------------------------

    def run_cmd(self, cmd, **env):
        with open(os.path.join(self.tmp, "scenario.json"), "w") as f:
            json.dump(self.scenario, f)
        full = dict(self.env)
        for key, value in env.items():
            if value is None:
                full.pop(key, None)
            else:
                full[key] = value
        return subprocess.run(cmd, env=full, capture_output=True, text=True, timeout=120)

    def lib(self, body, **env):
        return self.run_cmd([self.SHELL, "-c", 'source "%s"\n%s' % (LIB, body)], **env)

    def script(self, name, *args, **env):
        return self.run_cmd([self.SHELL, os.path.join(SCRIPTS, name)] + list(args), **env)

    def calls(self, tool):
        path = os.path.join(self.tmp, "calls.jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            rows = [json.loads(line) for line in f]
        return [r for r in rows if r["tool"] == tool]

    def mints(self):
        return [c for c in self.calls("az") if c["argv"][:2] == ["account", "get-access-token"]]

    def discoveries(self):
        return [c for c in self.calls("curl") if c["url"].endswith("/_apis/connectionData")]

    def api_calls(self):
        return [c for c in self.calls("curl") if API_URL in c["url"]]

    def assertOk(self, result):
        self.assertEqual(result.returncode, 0, "stdout=%r stderr=%r" % (result.stdout, result.stderr))

    def assertFailed(self, result):
        self.assertNotEqual(result.returncode, 0, "stdout=%r stderr=%r" % (result.stdout, result.stderr))


class AuthResolution(Fixture):
    def test_pat_uses_basic_auth_without_az_or_tenant_lookup(self):
        self.api(ok('{"count": 1}'))
        result = self.lib(API, AZURE_DEVOPS_EXT_PAT=PAT)
        self.assertOk(result)
        self.assertEqual(result.stdout.strip(), '{"count": 1}')
        self.assertEqual(self.api_calls()[0]["headers"]["authorization"], PAT_BASIC)
        self.assertEqual(self.mints(), [])
        self.assertEqual(self.discoveries(), [])

    def test_az_fallback_mints_for_the_org_tenant(self):
        token = jwt(ORG_TENANT)
        self.org_tenant()
        self.mint(token)
        self.api(ok())
        result = self.lib(API)
        self.assertOk(result)
        argv = self.mints()[0]["argv"]
        self.assertIn("--tenant", argv)
        self.assertEqual(argv[argv.index("--tenant") + 1], ORG_TENANT)
        self.assertEqual(argv[argv.index("--resource") + 1], RESOURCE)
        self.assertEqual(self.api_calls()[0]["headers"]["authorization"], "Bearer " + token)

    def test_tenant_lookup_sends_no_credentials(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT))
        self.api(ok())
        self.assertOk(self.lib(API))
        self.assertNotIn("authorization", self.discoveries()[0]["headers"])

    def test_tenant_header_name_is_case_insensitive(self):
        self.org_tenant(name="x-vss-resourcetenant")
        self.mint(jwt(ORG_TENANT))
        self.api(ok())
        self.assertOk(self.lib(API))
        argv = self.mints()[0]["argv"]
        self.assertEqual(argv[argv.index("--tenant") + 1], ORG_TENANT)

    def test_tenant_header_list_uses_first_real_tenant(self):
        self.org_tenant(value="%s, %s" % (NIL_TENANT, ORG_TENANT))
        self.mint(jwt(ORG_TENANT))
        self.api(ok())
        self.assertOk(self.lib(API))
        argv = self.mints()[0]["argv"]
        self.assertEqual(argv[argv.index("--tenant") + 1], ORG_TENANT)

    def test_nil_tenant_mints_without_tenant_flag(self):
        self.org_tenant(value=NIL_TENANT)
        self.mint(jwt(HOME_TENANT))
        self.api(ok())
        self.assertOk(self.lib(API))
        self.assertNotIn("--tenant", self.mints()[0]["argv"])

    def test_unreachable_org_mints_for_default_tenant_with_warning(self):
        self.route_curl("/_apis/connectionData", {"exit": 6, "stderr": "curl: (6) Could not resolve host\n"})
        self.mint(jwt(HOME_TENANT))
        self.api(ok())
        result = self.lib(API)
        self.assertOk(result)
        self.assertNotIn("--tenant", self.mints()[0]["argv"])
        self.assertIn("tenant", result.stderr.lower())

    def test_missing_tenant_header_mints_for_default_tenant(self):
        self.route_curl("/_apis/connectionData", SIGNIN_REDIRECT)
        self.mint(jwt(HOME_TENANT))
        self.api(ok())
        self.assertOk(self.lib(API))
        self.assertNotIn("--tenant", self.mints()[0]["argv"])

    def test_tenant_override_skips_lookup(self):
        self.mint(jwt(ORG_TENANT))
        self.api(ok())
        self.assertOk(self.lib(API, ADO_TENANT_ID=ORG_TENANT))
        self.assertEqual(self.discoveries(), [])
        argv = self.mints()[0]["argv"]
        self.assertEqual(argv[argv.index("--tenant") + 1], ORG_TENANT)

    def test_invalid_tenant_override_fails_before_az(self):
        result = self.lib(API, ADO_TENANT_ID="not-a-guid")
        self.assertFailed(result)
        self.assertIn("ADO_TENANT_ID", result.stderr)
        self.assertEqual(self.mints(), [])

    def test_tenant_lookup_repeats_when_org_changes(self):
        other = "https://dev.azure.com/other-org"
        self.org_tenant()
        self.org_tenant(value=HOME_TENANT, org=other)
        self.mint(jwt(ORG_TENANT), jwt(HOME_TENANT))
        body = ("ado_require_env; ado_resolve_auth; "
                "ADO_ORG=%s; ado_resolve_auth; echo \"$ADO_AUTH_HEADER\"" % other)
        result = self.lib(body)
        self.assertOk(result)
        self.assertEqual(len(self.discoveries()), 2)
        last = self.mints()[1]["argv"]
        self.assertEqual(last[last.index("--tenant") + 1], HOME_TENANT)

    def test_jwt_in_pat_variable_uses_bearer(self):
        token = jwt(ORG_TENANT)
        self.api(ok())
        self.assertOk(self.lib(API, AZURE_DEVOPS_EXT_PAT=token))
        self.assertEqual(self.api_calls()[0]["headers"]["authorization"], "Bearer " + token)
        self.assertEqual(self.mints(), [])

    def test_ado_token_uses_bearer(self):
        token = jwt(ORG_TENANT)
        self.api(ok())
        self.assertOk(self.lib(API, ADO_TOKEN=token))
        self.assertEqual(self.api_calls()[0]["headers"]["authorization"], "Bearer " + token)
        self.assertEqual(self.mints(), [])

    def test_lazy_resolution_without_explicit_call(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT))
        self.api(ok())
        self.assertOk(self.lib("ado_require_env; ado_api GET projects"))
        self.assertEqual(len(self.mints()), 1)

    def test_credentials_stay_out_of_curl_argv(self):
        token = jwt(ORG_TENANT)
        self.org_tenant()
        self.mint(token)
        self.api(ok())
        self.assertOk(self.lib(API))
        self.assertOk(self.lib(API, AZURE_DEVOPS_EXT_PAT=PAT))
        for call in self.calls("curl"):
            joined = " ".join(call["argv"])
            self.assertNotIn(token, joined)
            self.assertNotIn(PAT_BASIC.split()[1], joined)


class MintErrors(Fixture):
    def setUp(self):
        super().setUp()
        self.org_tenant()
        self.api(ok())

    def test_not_logged_in(self):
        self.mint_fails("ERROR: Please run 'az login' to setup account.\n")
        result = self.lib(API)
        self.assertFailed(result)
        self.assertIn("az login", result.stderr)
        self.assertEqual(self.api_calls(), [])

    def test_az_missing(self):
        self.uninstall("az")
        result = self.lib(API)
        self.assertFailed(result)
        self.assertIn("az", result.stderr)
        self.assertEqual(self.api_calls(), [])

    def test_expired_session_suggests_login_to_subscription_tenant(self):
        self.mint_fails("ERROR: AADSTS700082: The refresh token has expired due to inactivity.\n")
        self.route_az(["account", "show"], {"stdout": HOME_TENANT + "\n"})
        result = self.lib(API)
        self.assertFailed(result)
        self.assertIn("az login --tenant " + HOME_TENANT, result.stderr)

    def test_not_a_member_of_org_tenant(self):
        self.mint_fails("ERROR: AADSTS50020: User account from identity provider does not exist in tenant.\n")
        result = self.lib(API)
        self.assertFailed(result)
        self.assertIn(ORG_TENANT, result.stderr)
        self.assertIn("member or guest", result.stderr)

    def test_interaction_required_suggests_scoped_login_and_restore(self):
        self.mint_fails("ERROR: AADSTS50076: you must use multi-factor authentication.\n")
        result = self.lib(API)
        self.assertFailed(result)
        self.assertIn("az login --tenant %s --allow-no-subscriptions --scope %s/.default"
                      % (ORG_TENANT, RESOURCE), result.stderr)
        self.assertIn("az account set --subscription", result.stderr)
        self.assertIn("AADSTS50076", result.stderr)

    def test_unknown_error_is_shown(self):
        self.mint_fails("ERROR: something unexpected happened\n")
        result = self.lib(API)
        self.assertFailed(result)
        self.assertIn("something unexpected happened", result.stderr)

    def test_warning_lines_are_not_taken_as_the_token(self):
        token = jwt(ORG_TENANT)
        self.route_az(["account", "get-access-token"],
                      {"stdout": token + "\n", "stderr": "WARNING: a newer az CLI is available\n"})
        self.assertOk(self.lib(API))
        self.assertEqual(self.api_calls()[0]["headers"]["authorization"], "Bearer " + token)

    def test_empty_az_output_fails(self):
        self.route_az(["account", "get-access-token"], {"stdout": "\n"})
        result = self.lib(API)
        self.assertFailed(result)
        self.assertEqual(self.api_calls(), [])


class Responses(Fixture):
    def test_rejected_minted_token_is_reminted_once(self):
        first, second = jwt(ORG_TENANT, "first"), jwt(ORG_TENANT, "second")
        self.org_tenant()
        self.mint(first, second)
        self.api(status(401), ok('{"retried": true}'))
        result = self.lib(API)
        self.assertOk(result)
        self.assertEqual(result.stdout.strip(), '{"retried": true}')
        self.assertEqual(len(self.mints()), 2)
        calls = self.api_calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["headers"]["authorization"], "Bearer " + second)

    def test_second_rejection_fails_without_another_mint(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT, "first"), jwt(ORG_TENANT, "second"), jwt(ORG_TENANT, "third"))
        self.api(status(401))
        result = self.lib(API)
        self.assertFailed(result)
        self.assertEqual(len(self.mints()), 2)
        self.assertEqual(len(self.api_calls()), 2)
        self.assertIn("401", result.stderr)

    def test_same_token_after_remint_is_not_retried(self):
        token = jwt(ORG_TENANT)
        self.org_tenant()
        self.mint(token, token)
        self.api(status(401))
        result = self.lib(API)
        self.assertFailed(result)
        self.assertEqual(len(self.api_calls()), 1)

    def test_signin_redirect_is_an_auth_rejection(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT, "first"), jwt(ORG_TENANT, "second"))
        self.api(SIGNIN_REDIRECT, ok())
        self.assertOk(self.lib(API))
        self.assertEqual(len(self.api_calls()), 2)

    def test_html_on_a_read_is_an_auth_rejection(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT, "first"), jwt(ORG_TENANT, "second"))
        self.api(status(203, "<html>sign in</html>", "text/html; charset=utf-8"), ok())
        self.assertOk(self.lib(API))
        self.assertEqual(len(self.api_calls()), 2)

    def test_write_is_retried_after_401(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT, "first"), jwt(ORG_TENANT, "second"))
        self.route_curl("/_apis/wit/workItems/7/comments", status(401), ok('{"id": 1}'))
        result = self.lib("ado_require_env; ado_api POST wit/workItems/7/comments '{\"text\":\"hi\"}'")
        self.assertOk(result)
        self.assertEqual(len([c for c in self.calls("curl") if "/comments" in c["url"]]), 2)

    def test_write_is_not_retried_after_ambiguous_html(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT, "first"), jwt(ORG_TENANT, "second"))
        self.route_curl("/_apis/wit/workItems/7/comments",
                        status(502, "<html>Bad gateway</html>", "text/html"), ok('{"id": 1}'))
        result = self.lib("ado_require_env; ado_api POST wit/workItems/7/comments '{\"text\":\"hi\"}'")
        self.assertFailed(result)
        self.assertEqual(len([c for c in self.calls("curl") if "/comments" in c["url"]]), 1)
        self.assertEqual(len(self.mints()), 1)

    def test_rejected_pat_is_not_replaced(self):
        self.api(status(401))
        result = self.lib(API, AZURE_DEVOPS_EXT_PAT=PAT)
        self.assertFailed(result)
        self.assertIn("AZURE_DEVOPS_EXT_PAT", result.stderr)
        self.assertEqual(self.mints(), [])
        self.assertEqual(len(self.api_calls()), 1)

    def test_minted_marker_does_not_make_a_pat_refreshable(self):
        self.api(status(401))
        result = self.lib(API, AZURE_DEVOPS_EXT_PAT=PAT, ADO_TOKEN_MINTED="1")
        self.assertFailed(result)
        self.assertEqual(self.mints(), [])

    def test_rejected_user_token_is_not_replaced(self):
        self.api(SIGNIN_REDIRECT)
        result = self.lib(API, ADO_TOKEN=jwt(ORG_TENANT))
        self.assertFailed(result)
        self.assertIn("ADO_TOKEN", result.stderr)
        self.assertEqual(self.mints(), [])

    def test_token_from_wrapper_is_reminted(self):
        fresh = jwt(ORG_TENANT, "fresh")
        self.org_tenant()
        self.mint(fresh)
        self.api(status(401), ok())
        result = self.lib(API, ADO_TOKEN=jwt(ORG_TENANT, "stale"), ADO_TOKEN_MINTED="1")
        self.assertOk(result)
        self.assertEqual(len(self.mints()), 1)
        self.assertEqual(self.api_calls()[1]["headers"]["authorization"], "Bearer " + fresh)

    def test_wrong_tenant_names_both_tenants(self):
        token = jwt(HOME_TENANT, "xy")
        self.assertNotEqual(len(token.split(".")[1]) % 4, 0, "fixture should need base64 padding")
        self.org_tenant()
        self.api(status(403, MATERIALIZED))
        result = self.lib(API, ADO_TOKEN=token)
        self.assertFailed(result)
        self.assertIn(HOME_TENANT, result.stderr)
        self.assertIn(ORG_TENANT, result.stderr)
        self.assertEqual(self.mints(), [])

    def test_wrong_tenant_with_unreadable_token_still_names_org_tenant(self):
        self.org_tenant()
        self.api(status(403, MATERIALIZED))
        result = self.lib(API, ADO_TOKEN="eyJnot.a-valid.token")
        self.assertFailed(result)
        self.assertIn(ORG_TENANT, result.stderr)

    def test_http_error_body_goes_to_stderr(self):
        self.api(status(404, '{"message": "project not found"}'))
        result = self.lib(API, AZURE_DEVOPS_EXT_PAT=PAT)
        self.assertFailed(result)
        self.assertEqual(result.stdout, "")
        self.assertIn("404", result.stderr)
        self.assertIn("project not found", result.stderr)

    def test_transport_failure_is_not_retried(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT, "first"), jwt(ORG_TENANT, "second"))
        self.api({"exit": 7, "stderr": "curl: (7) Failed to connect\n"})
        result = self.lib(API)
        self.assertFailed(result)
        self.assertEqual(len(self.api_calls()), 1)
        self.assertEqual(len(self.mints()), 1)

    def test_empty_success_body(self):
        self.route_curl("/_apis/wit/workItems/7/comments/3", status(204, "", ""))
        result = self.lib("ado_require_env; ado_api DELETE wit/workItems/7/comments/3",
                          AZURE_DEVOPS_EXT_PAT=PAT)
        self.assertOk(result)
        self.assertEqual(result.stdout, "")

    def test_method_and_body_are_sent(self):
        self.route_curl("/_apis/wit/workItems/7/comments", ok('{"id": 1}'))
        result = self.lib("ado_require_env; ado_api POST wit/workItems/7/comments '{\"text\":\"hi\"}'",
                          AZURE_DEVOPS_EXT_PAT=PAT)
        self.assertOk(result)
        call = self.calls("curl")[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["data"], '{"text":"hi"}')
        self.assertEqual(call["headers"]["content-type"], "application/json")
        self.assertTrue(call["url"].endswith("/comments?api-version=7.1"))


class Scripts(Fixture):
    def run_two_requests(self, **env):
        self.route_curl("/_apis/build/builds/7/timeline", ok('{"records": []}'))
        self.route_curl("/_apis/build/builds/7", ok('{"buildNumber": "7", "definition": {"name": "ci"}}'))
        return self.script("ado-get-run.sh", "--run-id", "7", **env)

    def build_auth_headers(self):
        return [c["headers"]["authorization"] for c in self.calls("curl") if "/_apis/build/builds/7" in c["url"]]

    def test_expired_wrapper_token_is_reminted_once_before_requests(self):
        fresh = jwt(ORG_TENANT, "fresh")
        self.org_tenant()
        self.mint(fresh)
        result = self.run_two_requests(ADO_TOKEN=jwt(ORG_TENANT, "stale", exp=int(time.time()) - 60),
                                       ADO_TOKEN_MINTED="1")
        self.assertOk(result)
        self.assertEqual(len(self.mints()), 1)
        self.assertEqual(self.build_auth_headers(), ["Bearer " + fresh] * 2)

    def test_wrapper_token_close_to_expiry_is_reminted(self):
        fresh = jwt(ORG_TENANT, "fresh")
        self.org_tenant()
        self.mint(fresh)
        result = self.run_two_requests(ADO_TOKEN=jwt(ORG_TENANT, "ending", exp=int(time.time()) + 120),
                                       ADO_TOKEN_MINTED="1")
        self.assertOk(result)
        self.assertEqual(self.build_auth_headers(), ["Bearer " + fresh] * 2)

    def test_valid_wrapper_token_is_kept(self):
        token = jwt(ORG_TENANT, "valid", exp=int(time.time()) + 3600)
        result = self.run_two_requests(ADO_TOKEN=token, ADO_TOKEN_MINTED="1")
        self.assertOk(result)
        self.assertEqual(self.mints(), [])
        self.assertEqual(self.build_auth_headers(), ["Bearer " + token] * 2)

    def test_expired_supplied_token_is_not_replaced(self):
        token = jwt(ORG_TENANT, "supplied", exp=int(time.time()) - 60)
        result = self.run_two_requests(ADO_TOKEN=token)
        self.assertOk(result)
        self.assertEqual(self.mints(), [])
        self.assertEqual(self.build_auth_headers(), ["Bearer " + token] * 2)

    def test_script_mints_once_for_several_requests(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT))
        self.route_curl("/_apis/build/builds/7/timeline", ok('{"records": []}'))
        self.route_curl("/_apis/build/builds/7", ok('{"buildNumber": "7", "definition": {"name": "ci"}}'))
        result = self.script("ado-get-run.sh", "--run-id", "7")
        self.assertOk(result)
        self.assertEqual(len(self.mints()), 1)
        self.assertEqual(len(self.discoveries()), 1)


class Exec(Fixture):
    def dumped(self, result):
        self.assertOk(result)
        return json.loads(result.stdout)

    def test_help_exits_zero(self):
        result = self.script("ado-exec.sh", "--help")
        self.assertOk(result)
        self.assertIn("Usage", result.stdout)

    def test_command_is_required(self):
        result = self.script("ado-exec.sh")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Usage", result.stderr)

    def test_unknown_flag_is_rejected(self):
        result = self.script("ado-exec.sh", "--bogus", "--", "true")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--bogus", result.stderr)

    def test_real_pat_passes_through(self):
        env = self.dumped(self.script("ado-exec.sh", "--", *DUMP_ENV, AZURE_DEVOPS_EXT_PAT=PAT))
        self.assertEqual(env["AZURE_DEVOPS_EXT_PAT"], PAT)
        self.assertIsNone(env["ADO_TOKEN"])
        self.assertIsNone(env["ADO_TOKEN_MINTED"])
        self.assertEqual(self.calls("az"), [])
        self.assertEqual(self.calls("curl"), [])

    def test_minted_token_is_exported_to_the_command(self):
        token = jwt(ORG_TENANT)
        self.org_tenant()
        self.mint(token)
        env = self.dumped(self.script("ado-exec.sh", "--", *DUMP_ENV))
        self.assertEqual(env["ADO_TOKEN"], token)
        self.assertEqual(env["AZURE_DEVOPS_EXT_PAT"], token)
        self.assertEqual(env["ADO_AUTH_HEADER"], "Authorization: Bearer " + token)
        self.assertEqual(env["ADO_TOKEN_MINTED"], "1")

    def test_supplied_token_is_kept(self):
        token = jwt(ORG_TENANT, "supplied")
        env = self.dumped(self.script("ado-exec.sh", "--", *DUMP_ENV, ADO_TOKEN=token))
        self.assertEqual(env["ADO_TOKEN"], token)
        self.assertEqual(env["AZURE_DEVOPS_EXT_PAT"], token)
        self.assertIsNone(env["ADO_TOKEN_MINTED"])
        self.assertEqual(self.mints(), [])

    def test_project_is_not_required(self):
        self.org_tenant()
        self.mint(jwt(ORG_TENANT))
        self.dumped(self.script("ado-exec.sh", "--", *DUMP_ENV, ADO_PROJECT=None))

    def test_org_flag_overrides_environment(self):
        other = "https://dev.azure.com/other-org"
        self.org_tenant(org=other)
        self.mint(jwt(ORG_TENANT))
        env = self.dumped(self.script("ado-exec.sh", "--org", other + "/", "--", *DUMP_ENV))
        self.assertEqual(env["ADO_ORG"], other)
        self.assertEqual(self.discoveries()[0]["url"], other + "/_apis/connectionData")

    def test_missing_org_fails(self):
        result = self.script("ado-exec.sh", "--", "true", ADO_ORG=None)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ADO_ORG", result.stderr)

    def test_command_exit_code_is_kept(self):
        result = self.script("ado-exec.sh", "--", "sh", "-c", "exit 7", AZURE_DEVOPS_EXT_PAT=PAT)
        self.assertEqual(result.returncode, 7)

    def test_command_does_not_run_when_mint_fails(self):
        marker = os.path.join(self.tmp, "ran")
        self.org_tenant()
        self.mint_fails("ERROR: Please run 'az login' to setup account.\n")
        result = self.script("ado-exec.sh", "--", "touch", marker)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(os.path.exists(marker))


def _shells():
    found = {}
    for candidate in (shutil.which("bash"), "/bin/bash"):
        if candidate and os.path.exists(candidate):
            found.setdefault(os.path.realpath(candidate), candidate)
    return list(found.values())


def _major(shell):
    out = subprocess.run([shell, "-c", "echo ${BASH_VERSINFO[0]}"], capture_output=True, text=True)
    return out.stdout.strip()


for _shell in _shells():
    for _group in (AuthResolution, MintErrors, Responses, Scripts, Exec):
        _name = "%sBash%s" % (_group.__name__, _major(_shell))
        globals()[_name] = type(_name, (_group, unittest.TestCase), {"SHELL": _shell})
