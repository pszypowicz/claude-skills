# One-time setup details

The main skill covers creating the API key and running `setup`. This file
covers the parts that only some consoles need.

## Pinning a self-signed certificate

A console that still serves its stock self-signed certificate fails standard
TLS verification. Pin that certificate by its SHA-256 fingerprint instead.

1. Read the fingerprint the console presents. This connects without verifying
   the certificate and sends no request, so the API key is not involved.

   ```sh
   unifi cert-fingerprint --host <console-address>
   ```

2. Confirm the value with the user before trusting it. On a LAN they control,
   accepting it on first use is the usual trade-off. A stricter check is to
   read the fingerprint again from a second machine, for example with
   `openssl s_client -connect <console-address>:443 </dev/null | openssl x509 -noout -fingerprint -sha256`,
   and compare.

3. Save it with the host:

   ```sh
   unifi setup --host <console-address> --cert-sha256 <fingerprint>
   ```

The fingerprint accepts colon-separated hex in either case and the
`sha256 Fingerprint=...` line that openssl prints. A pinned connection accepts
exactly that certificate under any host name or IP, so the console can be
configured by its IP address.

A pin stops working when the console's certificate changes, which happens after
a factory reset or when a new certificate is installed. Running `setup` for a
different host drops the old pin. To go back to standard verification for the
same host, delete `cert_sha256` from `config.json`.

## Enabling SSH on the console

`unifi-ssh` needs SSH enabled in the UniFi OS console settings, with a password
set there. The setting's location moves between UniFi OS releases. The user is
`root` on UniFi OS consoles.

## An ssh Host block for the console

`unifi-ssh` names the host and leaves everything else to the ssh configuration.
The `Host` pattern has to match the address `unifi-ssh` connects to, which is
the same host the API client uses (`--host`, `UNIFI_HOST`, or the saved
config).

```sshconfig
Host unifi.lan.example.net
  User root
  # A border router is the last place to expose the agent socket.
  ForwardAgent no
  # Password-only host, so the key agent is never consulted.
  PubkeyAuthentication no
  IdentityAgent none
  # The console advertises keyboard-interactive. Password is listed too
  # because PAM configuration varies across firmware.
  PreferredAuthentications keyboard-interactive,password
  # A wrong password fails once instead of looping through the askpass helper.
  NumberOfPasswordPrompts 1
  StrictHostKeyChecking accept-new
  # OpenSSH 10.1 or newer. The console offers no post-quantum key exchange,
  # and without this every connection prints a warning about it.
  WarnWeakCrypto no-pq-kex
```

Drop the `WarnWeakCrypto` line on OpenSSH older than 10.1, which rejects the
option.

`unifi-ssh` delivers the password through the `SSH_ASKPASS` interface. Its
helper answers only prompts that ask for a password, so a host key
confirmation can never be answered with the password by accident.
