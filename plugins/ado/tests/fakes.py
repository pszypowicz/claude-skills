"""Fake curl and az executables for the ado client tests.

The tests put small wrappers named curl and az on PATH that run this file.
Each invocation is appended to calls.jsonl in FAKE_DIR, and the response
comes from scenario.json in the same directory. A route's responses are
served in order; the last one repeats once the list runs out.
"""

import json
import os
import sys

# curl options that take a value. Anything else starting with "-" is a flag.
CURL_VALUE_OPTS = {
    "-o", "--output", "-D", "--dump-header", "-w", "--write-out",
    "-K", "--config", "-H", "--header", "-X", "--request",
    "-d", "--data", "--data-raw", "--data-binary", "-m", "--max-time",
    "--connect-timeout", "-u", "--user", "-A", "--user-agent",
}


def fake_dir():
    return os.environ["FAKE_DIR"]


def load_scenario():
    with open(os.path.join(fake_dir(), "scenario.json")) as f:
        return json.load(f)


def record(call):
    with open(os.path.join(fake_dir(), "calls.jsonl"), "a") as f:
        f.write(json.dumps(call) + "\n")


def next_response(key, responses):
    """Return the next response for a route, advancing its counter."""
    path = os.path.join(fake_dir(), "state.json")
    state = {}
    if os.path.exists(path):
        with open(path) as f:
            state = json.load(f)
    count = state.get(key, 0)
    state[key] = count + 1
    with open(path, "w") as f:
        json.dump(state, f)
    return responses[min(count, len(responses) - 1)]


def parse_config(text):
    """Parse curl config lines such as: header = "Authorization: Bearer x"."""
    pairs = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, rest = line.partition(" ")
        name = name.rstrip("=:").lstrip("-")
        value = rest.strip().lstrip("=:").strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        pairs.append((name, value))
    return pairs


def curl(argv):
    opts = {"headers": [], "method": None, "data": None, "output": None,
            "dump_header": None, "write_out": None, "url": None}
    stdin_config = ""
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in CURL_VALUE_OPTS:
            value = argv[i + 1]
            i += 2
            if arg in ("-H", "--header"):
                opts["headers"].append(value)
            elif arg in ("-X", "--request"):
                opts["method"] = value
            elif arg in ("-d", "--data", "--data-raw", "--data-binary"):
                opts["data"] = value
            elif arg in ("-o", "--output"):
                opts["output"] = value
            elif arg in ("-D", "--dump-header"):
                opts["dump_header"] = value
            elif arg in ("-w", "--write-out"):
                opts["write_out"] = value
            elif arg in ("-K", "--config") and value == "-":
                stdin_config = sys.stdin.read()
            continue
        if arg.startswith("-"):
            i += 1
            continue
        opts["url"] = arg
        i += 1

    for name, value in parse_config(stdin_config):
        if name == "header":
            opts["headers"].append(value)
        elif name == "url":
            opts["url"] = value

    headers = {}
    for h in opts["headers"]:
        name, _, value = h.partition(":")
        headers[name.strip().lower()] = value.strip()
    method = opts["method"] or ("POST" if opts["data"] is not None else "GET")
    record({"tool": "curl", "argv": argv, "url": opts["url"], "method": method,
            "headers": headers, "data": opts["data"]})

    scenario = load_scenario()
    routes = scenario.get("curl", [])
    for index, route in enumerate(routes):
        if route["url_contains"] in (opts["url"] or ""):
            resp = next_response("curl-%d" % index, route["responses"])
            break
    else:
        sys.stderr.write("fake curl: no route for %s\n" % opts["url"])
        return 7

    if resp.get("exit", 0):
        sys.stderr.write(resp.get("stderr", "curl: (6) Could not resolve host\n"))
        return resp["exit"]

    status = resp.get("status", 200)
    content_type = resp.get("content_type", "application/json; charset=utf-8")
    body = resp.get("body", "")
    out = sys.stdout

    if opts["dump_header"] == "-":
        out.write("HTTP/1.1 %d Fake\r\n" % status)
        if content_type:
            out.write("Content-Type: %s\r\n" % content_type)
        if resp.get("location"):
            out.write("Location: %s\r\n" % resp["location"])
        for name, value in resp.get("headers", []):
            out.write("%s: %s\r\n" % (name, value))
        out.write("\r\n")

    if opts["output"] in (None, "-"):
        out.write(body)
    elif opts["output"] != "/dev/null":
        with open(opts["output"], "w") as f:
            f.write(body)

    if opts["write_out"] is not None:
        text = (opts["write_out"]
                .replace("\\n", "\n")
                .replace("\\t", "\t")
                .replace("%{http_code}", str(status))
                .replace("%{response_code}", str(status))
                .replace("%{redirect_url}", resp.get("location", ""))
                .replace("%{content_type}", content_type))
        out.write(text)
    return 0


def az(argv):
    record({"tool": "az", "argv": argv,
            "env": {k: os.environ.get(k) for k in (
                "AZURE_DEVOPS_EXT_PAT", "ADO_TOKEN", "AZURE_CONFIG_DIR",
                "AZURE_EXTENSION_DIR", "AZURE_DEVOPS_EXT_CONFIG_DIR")}})
    scenario = load_scenario()
    for index, route in enumerate(scenario.get("az", [])):
        match = route["match"]
        if argv[:len(match)] == match:
            resp = next_response("az-%d" % index, route["responses"])
            sys.stdout.write(resp.get("stdout", ""))
            sys.stderr.write(resp.get("stderr", ""))
            return resp.get("exit", 0)
    sys.stderr.write("fake az: no route for %s\n" % " ".join(argv))
    return 2


if __name__ == "__main__":
    tool, args = sys.argv[1], sys.argv[2:]
    sys.exit(curl(args) if tool == "curl" else az(args))
