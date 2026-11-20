---
name: unifi
description: Investigate a local UniFi console (Dream Machine, Cloud Key, or self-hosted Network application) over the LAN, using its Integration API first and SSH for what the API cannot reach. Use when the user asks about their UniFi router, gateway, switches, access points, connected clients, wireless topology, device firmware, port status, or network health, and also for firewall rules, routing tables, DHCP leases, console logs, connection tracking, Protect camera streams, or packet capture. Triggers on things like "check my UniFi", "what's on my network", "which clients are connected", "is my AP online", "what are my firewall rules". Read-only, so it inspects and reports and never changes configuration.
---

# UniFi console investigation

Read-only access to a UniFi console on the local network through its official
Integration API, with an SSH fallback for what the API does not expose. All
traffic stays on the LAN and nothing is sent to Ubiquiti's cloud.

## The tools

Two Python 3 scripts with no third-party dependencies. Both are on the `PATH`
while this plugin is enabled. If the shell cannot find them, they are in
`${CLAUDE_PLUGIN_ROOT}/bin/`.

- `unifi` is the API client and the one to reach for first.
- `unifi-ssh` runs a fixed list of diagnostics on the console over SSH.

Run `unifi --help` for the full flag list. Common flags (`--host`, `--site`,
`--format`, `--timeout`, `--max-records`, `--cert-sha256`) are accepted on
either side of the command word.

| Command                  | What it returns                                                                   |
| ------------------------ | --------------------------------------------------------------------------------- |
| `setup`                  | Stores the console host, and the API key where there is a Keychain.               |
| `info`                   | Network application version and metadata. Check this first when an endpoint 404s. |
| `sites`                  | Sites on the console, with the ids other commands take.                           |
| `devices`                | Every adopted device: name, model, IP, state, MAC, firmware.                      |
| `device --id <id>`       | One device in full, including uplink, ports, and radios.                          |
| `device-stats --id <id>` | Latest counters for one device: uptime, throughput, CPU, memory.                  |
| `clients`                | Currently connected clients with IP, MAC, and connection type.                    |
| `client --id <id>`       | One client in full.                                                               |
| `get --path <path>`      | Raw GET against any `integration/v1` path, for endpoints without a command.       |
| `cert-fingerprint`       | SHA-256 fingerprint of the console's certificate, for pinning a self-signed one.  |

Output is JSON by default, which suits analysis. Add `--format table` when
showing a list to the user.

## Credentials

The tools read secrets from the environment and never take them as arguments.

- `unifi` reads the API key from `UNIFI_API_KEY`. On macOS it falls back to the
  login Keychain entry that `setup` stores.
- `unifi-ssh` reads the console's SSH password from `UNIFI_SSH_PASSWORD` and
  has no fallback.

Before the first call, check whether the user's instructions or another loaded
skill describe how these variables are supplied on this machine. A secret
manager that wraps one command and sets the variable for it is the usual
arrangement. Follow that description, and ask the user when there is none.

Never put the key or the password on a command line, echo it, or write it to a
file. `setup` never copies a key it found in the environment into the Keychain,
because that would fork the secret into a second store that needs its own
rotation.

## Setup, once per console

The API key has to be created in the console UI, because no API mints one. In
the Network application, open Settings, then Control Plane, then Integrations.
The key is shown exactly once. It is bound to the admin account that created it
and stops working if that account is removed or loses permissions.

Then run `setup`, which verifies the key with a live call and caches the
default site:

```sh
unifi setup --host <console-address>
```

With `UNIFI_API_KEY` set, `setup` uses it and stores only the host. Without it,
`setup` prompts for the key and saves it in the macOS Keychain. Other platforms
have no Keychain fallback, so the variable is required there.

The host, the default site, and any pinned certificate fingerprint live in
`$XDG_CONFIG_HOME/unifi/config.json` (falling back to `~/.config/unifi/`). No
secret is ever written there.

[references/setup.md](references/setup.md) covers the rest of the one-time
work: pinning a self-signed certificate, enabling SSH on the console, and an
example ssh `Host` block.

## TLS

By default `unifi` verifies the console's certificate against the system trust
store and checks the host name. That works when the console serves a publicly
trusted certificate and is configured by a DNS name that the certificate covers.

A console with its stock self-signed certificate fails that check. Pin the
certificate instead with `--cert-sha256`, `UNIFI_CERT_SHA256`, or a fingerprint
saved by `setup`. A pinned connection accepts exactly that certificate, under
any host name or IP, and checks it before the API key is sent. The pinning steps
are in [references/setup.md](references/setup.md).

## Reporting results

The gateway's `ipAddress` in `devices` output is its WAN address. Treat it as
sensitive and never put it in a commit message, issue, PR, or anything else that
leaves the machine. The same goes for client MAC addresses and the console's
remote-access domain.

## Read-only guarantee

The HTTP layer issues GET and nothing else, so no API command can change console
state. Say so plainly if the user asks whether it is safe to run.

The SSH path is weaker and should be described honestly. `unifi-ssh` will only
build command lines from its own fixed list, but the session is root on the
console, so that is a guardrail in the client and nothing the console enforces.

Configuration changes are out of scope on both paths. When the user wants one,
walk them through the UI, or discuss adding a separate write path first. Do not
reach for the private `/proxy/network/api/s/<site>/...` endpoints from this
skill.

## The SSH path

`unifi-ssh` answers what the API cannot: applied firewall rules, kernel and
service logs, DHCP leases, connection tracking, Protect camera streams and
recordings, live packet capture, and the full on-disk configuration.

**Try the API first, every time.** SSH returns text instead of JSON and holds a
root session on the border router. Reach for it only when the API has no answer.

```sh
unifi-ssh list                     # available checks
unifi-ssh run --check iptables
```

When the password comes from a wrapper that asks the user for approval, put
related checks in one single-quoted `sh -c` under that wrapper so the user
approves once. The single quotes keep the outer shell from expanding anything
before the wrapper sets the variable.

```sh
sh -c 'unifi-ssh run --check routes; unifi-ssh run --check leases'
```

Useful flags are `--lines` for `journal`, `dmesg`, and the log checks, `--head`
to cap printed output (400 lines by default, `0` for everything), and `--dry-run`
to see the exact remote command without connecting.

`unifi-ssh` connects to the same host as `unifi` and takes everything else (user,
port, authentication, host key policy) from the standard ssh configuration.

### Before running anything sensitive

`tcpdump` and `mca-dump` require `--confirm`, and that flag means the user has
been asked. `tcpdump` records real traffic. `mca-dump` output contains WiFi
passphrases and other secrets, so summarize findings from it and never paste it
back verbatim.

### One attempt, then wait

Each SSH call is a single attempt with a timeout. If it hangs or fails, report
that and wait for the user. Do not retry in a loop, and do not look for another
way in.

### Firmware differences

Checks are named for tools that not every firmware ships. `nft` is absent where
filtering is done with iptables, and the DHCP lease path moves between releases.
Run the `available` check to see what a given console actually has, especially
after a firmware upgrade.

## Investigation notes

- Get `sites` first on an unfamiliar console. Most home setups have one site and
  the id is cached at setup, so `--site` is rarely needed.
- `devices` gives the inventory and `device --id` gives the depth. Go to the
  detail call for port-level or radio-level questions, because the list view
  omits them.
- Paged endpoints are followed automatically, `get --path` included. Cap large
  result sets with `--max-records` when a full sweep is not needed.
- For endpoints this tool has no command for, use `get --path`. The Integration
  API is versioned under `/proxy/network/integration/v1`, and `--path` is taken
  relative to that root unless it starts with a slash.
- On a paged endpoint `get --path` prints a plain array of every record, the
  same shape as `devices` and `clients`, and drops the `totalCount` envelope.
  If the path sets `offset` or `limit` itself, `get` returns that one page with
  its envelope and prints a note on stderr when records lie outside it. Other
  query parameters such as `filter` are kept on every page.

## Troubleshooting

**401** means the key was rejected. Keys are revoked when the admin account
that owns them is removed or its permissions drop. Create a new key and re-run
`setup`.

**404 on an endpoint that should exist** usually means the console is too old.
The Integration API needs UniFi Network 9.0 or newer. Confirm with `info`.

**TLS certificate verification failed** comes from standard verification. Common
causes are a host name or IP that the certificate does not cover, an expired
certificate, or a console that serves a self-signed certificate again after a
factory reset. Interception looks the same. Inspect what the console serves
with `openssl s_client`, fix the cause or pin the certificate, and only then
retry.

**Pinned fingerprint does not match** means the console presented a different
certificate than the one pinned. A reset or a replaced certificate explains it,
and so does interception. Confirm with the user which it is before pinning the
new value.

**Connection timeouts** point at the network rather than the API. Confirm the
console is reachable and that the machine is on the LAN and not routed through
a VPN that excludes the local subnet.

**SSH host key verification failed** is standard known_hosts handling. A
firmware reinstall explains it and so does an interception attempt. Confirm
with the user that the console really changed, then remove the stale entry
with `ssh-keygen -R <console-address>`.

**SSH password rejected** means `UNIFI_SSH_PASSWORD` no longer matches the SSH
password in the UniFi OS console settings. Changing the password in the UI does
not update wherever the variable comes from.

**`Permission denied (publickey,keyboard-interactive)`** means no authentication
method matched. The console advertises keyboard-interactive rather than
password, so the ssh `Host` block should request both.

## Related

Ubiquiti consoles answer `GET /api/system` without authentication on the LAN,
returning the model, MAC, and remote-access domain. That is stock behavior and
no misconfiguration, but it is worth knowing when discussing exposure.
