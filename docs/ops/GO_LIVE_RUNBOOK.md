# Parsec — Go-Live Runbook

**Audience:** Brian (sole dev), running on a personal Windows 10 home PC behind a
consumer router, with Norton Antivirus present.

**What this covers:** taking the SW_MUSH ("Parsec") aiohttp server from
"runs on localhost" to "publicly reachable on the internet, with TLS, an
auto-restarting service, backups, and a monitoring/rollback story." It is an
ordered checklist a solo dev can follow top to bottom.

**Ground truth about the server (do not assume otherwise):**

| Fact | Value | Source |
| --- | --- | --- |
| Entry point | `python main.py` (`asyncio.run(main())`) | `main.py:182-194` |
| Web bind (HTTP + WS, one port) | `0.0.0.0:8080` | `server/config.py:17-18`, `server/web_client.py:209` |
| WebSocket route | `/ws` (same port as HTTP) | `server/web_client.py:176` |
| Telnet bind (cleartext auth) | `0.0.0.0:4000` | `server/config.py:13-14`, `server/game_server.py:877` |
| TLS in server | **NONE** — plain HTTP/WS only | `web_client.py:209` (no `ssl_context`) |
| Port override | `--web-port` CLI flag only | `main.py:62-65` |
| Host override | **NOT exposed** via CLI/env — must edit `config.py` | gap "Public bind surface" |
| DB | single SQLite file `sw_mush.db` (WAL mode), `--db PATH` to override | `config.py:21`, `database.py:1612-1624` |
| Process supervision | **NONE** — dies on crash, no auto-restart | `main.py:158-160` |
| Session secret | `token_secret.key` (HMAC, 0600, auto-generated, gitignored) | `api.py:57-119` |
| Passwords | bcrypt per-hash salt | `database.py:1837-1838` |
| Director LLM cap | $20/mo, circuit breaker at 90% ($18) | `ai/claude_provider.py:12,82,256-259` |
| venv python | `c:\SW_MUSH\venv\Scripts\python.exe` | verified on box |

> The application layer is mature (bcrypt, HMAC tokens, CSP + security headers,
> request-size cap, sliding-window per-IP rate limits, env/file-based secrets).
> The **hosting envelope** is the missing work: TLS, localhost bind, and service
> supervision. This runbook closes that gap.

---

## DECISIONS NEEDED FROM BRIAN (resolve before starting)

- **[TODO — BRIAN] Domain name.** Pick and register a domain (or a free
  subdomain). Referenced below as `parsec.example.com`. See Section 3.
- **[TODO — BRIAN] Exposure path: Cloudflare Tunnel (Section 1, RECOMMENDED) vs.
  reverse proxy + port-forward (Section 2).** Tunnel is the default for a home PC
  on a dynamic IP — no port-forwarding, no exposed home IP, free TLS. Pick the
  proxy path only if you have a real reason (see Section 2 tradeoffs).
- **[TODO — BRIAN] Telnet:** keep it for admins/purists or kill it for launch?
  Either way it must NOT be on the public internet (cleartext auth). See
  Section 1.7 / Section 2.6.
- **[TODO — BRIAN] Cloudflare account** (free tier is fine) if taking the tunnel
  path.

---

## 0. One-time prep (both paths)

1. **Confirm the server runs locally first.** From `c:\SW_MUSH`:
   ```
   venv\Scripts\python.exe main.py --web-port 8080
   ```
   Browse `http://localhost:8080/` → the Parsec portal should load. `Ctrl+C` to
   stop. Do not proceed until this works.

2. **Decide the bind host.** Today the server binds `0.0.0.0` (all interfaces)
   and there is **no CLI/env knob for the host** — `--web-host` does not exist.
   For a hardened deploy you want the app reachable only from the local tunnel /
   proxy, i.e. bound to `127.0.0.1`. Two options:

   - **Option A (recommended): leave `0.0.0.0` but never port-forward 8080.**
     With the Cloudflare Tunnel (Section 1) the box's 8080 is never exposed to
     the internet — the router has no forward and Cloudflare reaches the app from
     the localhost-side `cloudflared` process. `0.0.0.0` is then only reachable
     from your LAN, which is acceptable. Simplest; no code change.

   - **Option B (defense-in-depth): bind localhost-only.** Edit
     `server/config.py:17` `web_client_host: str = "0.0.0.0"` →
     `"127.0.0.1"` and `server/config.py:13` `telnet_host` likewise. This is a
     one-line, additive-safe edit (changing a default literal, not deleting). It
     guarantees nothing on the LAN can reach the app directly either. **[TODO —
     BRIAN: pick A or B.]** If you want a proper knob instead of editing the
     dataclass, that is a small follow-up drop (add `--web-host` / `SWMUSH_WEB_HOST`);
     log it as a design call rather than guessing here.

   > Note: `cloudflared` connects to whatever host:port you give it
   > (`http://127.0.0.1:8080` or `http://localhost:8080`), so Option B is fully
   > compatible with the tunnel.

3. **Run the full test suite green** (the real launch gate — see Section 7
   before flipping anything public).

---

## 1. PRIMARY PATH — Cloudflare Tunnel (RECOMMENDED)

**Why this is the default for a home PC:** no router port-forwarding, no static
public IP needed, free automatic TLS at Cloudflare's edge, and your home IP is
hidden (Cloudflare is the only thing the public talks to). The tunnel is an
outbound-only connection from `cloudflared` on your box to Cloudflare, so nothing
inbound has to be opened on the router or firewall.

**Architecture:**
```
player browser  --HTTPS/WSS-->  Cloudflare edge  --tunnel-->  cloudflared (your box)  --HTTP/WS-->  127.0.0.1:8080 (aiohttp)
```
TLS is terminated at Cloudflare. The hop from `cloudflared` to the aiohttp server
is plain HTTP on localhost, which is fine (never leaves the machine).

### 1.1 Install cloudflared on Windows

Use winget (preferred) or the signed MSI:
```
winget install --id Cloudflare.cloudflared
```
Or download the `cloudflared-windows-amd64.msi` from Cloudflare's GitHub releases
and run it. Verify:
```
cloudflared --version
```

> **Norton caveat:** Norton may flag a freshly downloaded `cloudflared.exe` /
> block its first outbound connection. If install or `tunnel run` fails oddly,
> add a Norton exclusion for the cloudflared binary and allow its outbound
> connection. (Same class of issue as the Norton TLS interception that broke the
> Anthropic API until truststore was added — see Section 5.)

### 1.2 Authenticate to Cloudflare

```
cloudflared tunnel login
```
This opens a browser; log in and authorize the **zone** for your domain (you must
have added the domain to Cloudflare first — see Section 3). It writes a cert to
`%USERPROFILE%\.cloudflared\cert.pem`.

> **[TODO — BRIAN]** Requires the Cloudflare account + domain decision resolved.

### 1.3 Create a named tunnel

```
cloudflared tunnel create parsec
```
This creates the tunnel and writes a **credentials JSON** (the tunnel's secret)
to `%USERPROFILE%\.cloudflared\<TUNNEL-UUID>.json`. Note the UUID it prints —
you need it below. **Treat that JSON like a password** (do not commit it; it is
outside the repo by default, keep it that way).

### 1.4 Map a hostname (DNS route)

```
cloudflared tunnel route dns parsec parsec.example.com
```
This creates a proxied CNAME in Cloudflare DNS pointing your hostname at the
tunnel. (Replace `parsec.example.com` with the real domain — **[TODO — BRIAN].**)

### 1.5 Write the config file

Create `%USERPROFILE%\.cloudflared\config.yml`:
```yaml
tunnel: parsec
credentials-file: C:\Users\btgla\.cloudflared\<TUNNEL-UUID>.json

ingress:
  - hostname: parsec.example.com
    service: http://127.0.0.1:8080
    originRequest:
      # WebSocket (/ws) works over the tunnel by default; no extra config needed.
      # Generous timeouts so long-lived game WS sessions are not reaped.
      connectTimeout: 30s
      noTLSVerify: false
  - service: http_status:404
```
- `service: http://127.0.0.1:8080` is the real aiohttp bind from the audit
  (`web_client.py:209`). If you chose bind Option A in 0.2 you can use
  `http://localhost:8080` equivalently.
- WebSockets are tunneled transparently — the single-port HTTP+WS design
  (`/ws` on 8080) needs no special handling here, unlike a hand-rolled nginx
  config.

Test it in the foreground before installing as a service:
```
cloudflared tunnel run parsec
```
Browse `https://parsec.example.com/` from your phone on cellular (not your LAN) →
the portal should load over HTTPS. `Ctrl+C` to stop.

### 1.6 Run cloudflared as a Windows service (always-on)

```
cloudflared service install
```
On Windows this registers cloudflared as a service that reads
`%USERPROFILE%\.cloudflared\config.yml` and starts on boot. Manage it like any
service:
```
sc query cloudflared
sc stop  cloudflared
sc start cloudflared
```
Now the tunnel survives reboots independently of the game server (which gets its
own NSSM service in Section 4).

### 1.7 Telnet under the tunnel

The Cloudflare HTTP tunnel does **not** expose telnet (4000) — good. Telnet stays
LAN-only / localhost as configured. **Do not** add a TCP tunnel ingress for it
unless you deliberately want remote admin telnet, and if you do, gate it behind
Cloudflare Access (auth at the edge), never raw. **[TODO — BRIAN: confirm telnet
stays LAN-only.]**

---

## 2. ALTERNATIVE PATH — Reverse proxy + Let's Encrypt + port-forward + DDNS

**When to pick this over the tunnel:**
- You want zero third-party dependency in the request path (no Cloudflare edge).
- You need raw TCP exposure the tunnel can't easily do, or a corporate/policy
  reason to self-terminate TLS.
- You already run a proxy box / VPS you trust.

**Tradeoffs (why it is NOT the default for a home PC):**
- **Exposes your home IP** to every visitor (the tunnel hides it).
- **Requires router port-forwarding** (80/443 → your box) — many ISPs use CGNAT,
  which makes inbound port-forward impossible without the tunnel anyway.
- **Requires Dynamic DNS** because a home connection's public IP changes.
- You own cert renewal, firewall rules, and the public attack surface.

### 2.1 Dynamic DNS (DDNS)

Home IPs rotate. Use a DDNS provider (e.g. Cloudflare DNS via a DDNS updater
script, No-IP, DuckDNS) so `parsec.example.com` always resolves to your current
public IP. Install its updater as a scheduled task / service.

### 2.2 Router port-forward

Forward external **443 (and 80 for the ACME HTTP-01 challenge)** to your box's
LAN IP. Do **NOT** forward 8080 or 4000 directly — only the proxy ports.

### 2.3 Caddy (recommended proxy — automatic Let's Encrypt)

Install Caddy (`winget install CaddyServer.Caddy`). `Caddyfile`:
```
parsec.example.com {
    reverse_proxy 127.0.0.1:8080 {
        # aiohttp serves HTTP + WS on the same port; Caddy upgrades /ws
        # transparently — no special websocket block needed.
    }
    encode gzip
    header {
        # HSTS is intentionally omitted in the app (web_client.py:46-48) and is
        # the proxy's job. Enable it ONLY once you are sure you will stay HTTPS.
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
}
```
Caddy auto-provisions and renews the Let's Encrypt cert. Run Caddy as a service
(`caddy` ships a Windows service install path; or wrap it with NSSM like the game
server in Section 4).

### 2.4 nginx alternative

If you prefer nginx, you must terminate TLS (certbot for the cert) **and** add the
explicit WebSocket upgrade headers for `/ws` (nginx does not upgrade
automatically):
```nginx
server {
    listen 443 ssl;
    server_name parsec.example.com;
    ssl_certificate     /path/fullchain.pem;
    ssl_certificate_key /path/privkey.pem;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location /ws {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 3600s;   # long-lived game WS
    }
}
```

### 2.5 Trusted-proxy wiring (CRITICAL for either proxy)

The app's per-IP throttles only honor `X-Forwarded-For` when the direct peer is
in `SWMUSH_TRUSTED_PROXIES` (`api.py:220-253`). **If you add a proxy but leave
`SWMUSH_TRUSTED_PROXIES` unset, every request looks like it comes from the proxy
IP and all rate limits collapse into one bucket.** Set it in the service
environment (Section 4/5):
```
SWMUSH_TRUSTED_PROXIES=127.0.0.1
```
(Set it to the proxy's source IP as the app sees it.) This is the proxy path's
equivalent of the Cloudflare path — under Cloudflare you'd instead trust
Cloudflare's connecting IP; with `cloudflared` running on the same box that is
`127.0.0.1` as well.

> **Verify end-to-end:** create accounts rapidly from two different external
> clients and confirm the chargen/login throttle keys off the real client, not a
> single shared bucket.

### 2.6 Telnet

Firewall telnet (4000) off from the public internet entirely (do not forward it),
or bind it localhost (`config.py:13` → `127.0.0.1`). It carries the same
cleartext-credential risk as plain HTTP.

---

## 3. Domain + DNS

1. **[TODO — BRIAN] Register a domain** (Namecheap, Cloudflare Registrar,
   Porkbun, etc.) or use a free subdomain. Pick the final hostname; this runbook
   uses `parsec.example.com` as the placeholder.
2. **Cloudflare path:** add the domain as a zone in your Cloudflare account and
   set the registrar's nameservers to Cloudflare's. Then
   `cloudflared tunnel route dns` (1.4) creates the proxied record automatically —
   you do not hand-edit DNS.
3. **Proxy path:** point an `A`/`AAAA` record at your DDNS-updated home IP (2.1).
4. Verify resolution before going live:
   ```
   nslookup parsec.example.com
   ```

---

## 4. Process supervision — the game server as an auto-restarting Windows service (NSSM)

The server has **no** supervision today — if `main.py` crashes or the box reboots,
it stays down (`main.py:158-160`). Wrap it in NSSM so it auto-restarts and starts
on boot. This is the same OS-native approach `tools/durable_loop.py` already
proves works on this box (that tool uses Task Scheduler to supervise the
**Claude dev loop**, NOT the game server — do not confuse the two; this section
adds supervision for the *server itself*).

### 4.1 Install NSSM

```
winget install NSSM.NSSM
```
(or download `nssm.exe` and put it on PATH).

### 4.2 Create the service (use the REAL entry point + venv python + working dir)

```
nssm install ParsecServer "C:\SW_MUSH\venv\Scripts\python.exe" "C:\SW_MUSH\main.py" --web-port 8080 --db "C:\SW_MUSH\sw_mush.db"
nssm set ParsecServer AppDirectory "C:\SW_MUSH"
nssm set ParsecServer DisplayName "Parsec MUSH Server"
nssm set ParsecServer Description "SW_MUSH aiohttp game server (HTTP+WS on 8080)"
nssm set ParsecServer Start SERVICE_AUTO_START
```

- `AppDirectory` (working dir) MUST be `C:\SW_MUSH` because the default DB path is
  **relative to CWD** (`config.py:21`). Passing an absolute `--db` (above) makes
  it robust regardless, but set both.
- Using the **venv** python (`C:\SW_MUSH\venv\Scripts\python.exe`) is mandatory —
  the system `python3` (WindowsApps shim) does not have the project deps
  (aiohttp, aiosqlite, truststore, etc.).

### 4.3 Auto-restart on crash

```
nssm set ParsecServer AppExit Default Restart
nssm set ParsecServer AppRestartDelay 5000
nssm set ParsecServer AppThrottle 10000
```
- `AppExit Default Restart` → restart on any exit.
- `AppRestartDelay 5000` → wait 5s before restarting (avoid tight crash loops).
- `AppThrottle 10000` → if it dies within 10s of starting, back off (NSSM's
  crash-loop guard).

### 4.4 Log redirection

```
nssm set ParsecServer AppStdout "C:\SW_MUSH\logs\server.out.log"
nssm set ParsecServer AppStderr "C:\SW_MUSH\logs\server.err.log"
nssm set ParsecServer AppRotateFiles 1
nssm set ParsecServer AppRotateOnline 1
nssm set ParsecServer AppRotateBytes 10485760
```
(Create `C:\SW_MUSH\logs\` first.) The server logs via `logging` to stderr/stdout
(`main.py:40-49`), so these capture everything.

### 4.5 Service environment (secrets — see Section 5)

Set env vars the service runs with (one line, semicolon-separated `KEY=VALUE`
pairs). Do this so secrets are in the service environment, NOT in a logged shell:
```
nssm set ParsecServer AppEnvironmentExtra ANTHROPIC_API_KEY=sk-ant-... SWMUSH_TOKEN_SECRET_FILE=C:\SW_MUSH\secrets\token_secret.key SWMUSH_TRUSTED_PROXIES=127.0.0.1
```

### 4.6 Start / manage

```
nssm start ParsecServer
sc query ParsecServer
nssm restart ParsecServer
nssm stop ParsecServer
```
Windows has no SIGTERM the way POSIX does; `main.py` explicitly no-ops signal
handlers on Windows (`main.py:148-153`). NSSM stops the process cleanly via its
own shutdown sequence; the `while True: sleep` loop just ends. That is acceptable
here (SQLite WAL + `synchronous=NORMAL` is crash-safe; an abrupt stop loses only
in-flight uncommitted writes).

### 4.7 Order of operations

Bring up **cloudflared service first** (Section 1.6) **or** the proxy (Section 2),
then **ParsecServer**. Either order works since the tunnel/proxy retries until the
origin is up, but starting the origin first avoids 502s in the first few seconds.

---

## 5. Secrets / config hardening for production

**Principle:** nothing secret is hardcoded today (verified — `git ls-files` shows
`sw_mush.db`, `token_secret.key`, `*.key`, `.env/` all untracked/gitignored).
Keep it that way. Set secrets in the **service environment** (Section 4.5), never
in a committed file and never echoed into a shell that gets logged.

### 5.1 Required / recommended environment

| Var | Purpose | Required? |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Director AI (Haiku). Provider disables itself if unset (`claude_provider.py:323-325`). | Only if you want the Director live. |
| `SWMUSH_TOKEN_SECRET_FILE` | Path to the persisted HMAC login-token secret. | Recommended (see 5.2). |
| `SWMUSH_TRUSTED_PROXIES` | Proxy IP(s) so per-IP throttles see real clients. | **Yes** once a proxy/tunnel is in front (Sections 1/2). |
| `SWMUSH_MAX_REQUEST_BYTES` | Request body cap (default 256 KiB). | Optional. |
| `SWMUSH_DB_READ_POOL` | Read-only connection pool size (default 4). | Optional. |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | **Dev tooling only** (Nano mapgen). **Do NOT set in the server service.** | No. |

> **What must NOT be hardcoded:** the Anthropic key, the token secret, and DB
> credentials (there are none — SQLite is a local file). There is **no admin
> password file** — admin is a per-account DB flag, not a static credential, so
> there is nothing to set as an env secret for admin.

### 5.2 Token-secret durability (HIGH-priority gap)

`token_secret.key` persists the HMAC login-token key, but on any IO/permission
error the code **silently falls back to an ephemeral per-process secret**
(`api.py:78-83, 101-106`), which **invalidates every player's login token on the
next restart**. To make this durable:

1. Point `SWMUSH_TOKEN_SECRET_FILE` at a known, writable, protected path, e.g.
   `C:\SW_MUSH\secrets\token_secret.key` (create the `secrets\` dir).
2. Restrict its ACL to the service account (the file is written 0600 best-effort,
   which on Windows is only the read-only bit — set real ACLs with `icacls` to
   the account NSSM runs as).
3. After first start, **confirm the file exists and the ephemeral-fallback
   warning did NOT fire** in `logs\server.err.log` (grep for the
   "ephemeral"/fallback warning string). If it fired, fix permissions and
   restart before letting players in.

### 5.3 Config management reality

There is **no `.env`/YAML/config-file loader** despite the `config.py` docstring
("Load from YAML"). Production config is exactly: the `main.py` CLI flags
(`--web-port`, `--db`, `--log-level`) baked into the NSSM `Application` /
`AppParameters`, plus the `SWMUSH_*` env vars above. Everything else (host,
account limits, idle timeout, `era=clone_wars`, `use_yaml_director_data=True`) is
a compile-time constant in `config.py`. **Do not pass `--era` / `--use-yaml-director-data`
in production** — those are dev-only flags (`main.py:81-97`); the dataclass
defaults (`active_era="clone_wars"`, `use_yaml_director_data=True`,
`config.py:53-54`) are already the production values.

### 5.4 Norton AV / TLS caveat (learned the hard way)

Norton's Web/Mail Shield intercepts HTTPS and re-signs certs with a private root
in the **Windows** cert store, which `certifi`/aiohttp's default trust store does
not read → `CERTIFICATE_VERIFY_FAILED` on outbound calls to
`api.anthropic.com`. The fix is already in the code: `claude_provider.py:32-51`
builds a `truststore.SSLContext` that reads the OS store. **Production
requirement:** ensure `truststore` is installed in the venv
(`venv\Scripts\python.exe -m pip show truststore`); if it's missing, the Director
will silently fail its outbound TLS handshake on this Norton box. Also add Norton
exclusions for `cloudflared.exe` (Section 1.1) and `python.exe` if Norton
interferes with the listener.

---

## 6. SQLite production care

1. **WAL mode** is on by default (`database.py:1624`, `busy_timeout=5000`,
   `synchronous=NORMAL`). Confirm on the live file after first boot:
   ```
   venv\Scripts\python.exe -c "import sqlite3;print(sqlite3.connect('sw_mush.db').execute('pragma journal_mode').fetchone())"
   ```
   Expect `('wal',)`. You will see `sw_mush.db`, `sw_mush.db-wal`, and
   `sw_mush.db-shm` alongside each other — that is normal for WAL.

2. **File location:** keep the DB at `C:\SW_MUSH\sw_mush.db` and pass it
   absolutely via `--db` in the NSSM service (Section 4.2) so it does not depend
   on CWD.

3. **Scheduled backups (HIGH-priority gap — `backup_db.py` exists but is NOT
   wired).** Use the WAL-safe online backup tool — it is safe on a live DB
   (`tools/backup_db.py` → SQLite online backup API):
   ```
   venv\Scripts\python.exe tools\backup_db.py "C:\SW_MUSH\sw_mush.db" "C:\SW_MUSH\backups\sw_mush_%DATE%.db" --verify
   ```
   `--verify` runs the integrity scanner and exits non-zero on a corrupt/orphaned
   snapshot — never keep an unverified backup. Schedule it with Task Scheduler
   (the box's proven mechanism, same family `durable_loop.py` uses):
   ```
   schtasks /create /tn "ParsecBackup" /tr "C:\SW_MUSH\venv\Scripts\python.exe C:\SW_MUSH\tools\backup_db.py C:\SW_MUSH\sw_mush.db C:\SW_MUSH\backups\sw_mush_backup.db --overwrite --verify" /sc daily /st 04:00
   ```
   (Use a timestamped destination if you want to retain history rather than
   `--overwrite` a single rolling file; rotate/prune old ones yourself.)

4. **Periodic integrity check:** `tools/check_db_integrity.py` runs
   `PRAGMA integrity_check` + `foreign_key_check`. Run it weekly (own Task
   Scheduler entry) and after any migration.

5. **Restore runbook (already written — don't reinvent):** see
   `docs/design/backup_restore_runbook_v1.md`. In short: stop the service, copy
   the backup over `sw_mush.db`, **delete the stale `-wal`/`-shm` sidecars** so
   they can't replay over the restored file, verify with the integrity tool,
   restart.

6. **(Optional, future) continuous replication:** litestream-style streaming of
   the WAL to cloud storage gives point-in-time recovery beyond daily snapshots.
   Not required for launch scale (~4.4 MB DB); note as a post-launch upgrade.

---

## 7. Pre-flight checklist (the real launch gate — all must be true)

- [ ] **Full test suite green** on this box: `run_all_tests.bat` (~7,700+ tests).
      This is the gate, not targeted tests.
- [ ] **AST/syntax** clean on any touched file (e.g. if you applied bind Option B
      to `config.py`), and YAML valid on any touched data file.
- [ ] **Disclaimer present** (verified): portal footer carries
      "Unofficial fan project — not affiliated with Lucasfilm Ltd., The Walt
      Disney Company, or West End Games" (`static/portal.html:1387`). Confirm it
      still renders on the live portal.
- [ ] **Director $20/mo cap durable:** budget = 2000¢, circuit breaker at 90%
      ($18) (`claude_provider.py:12,82,256-259`). Spend is tracked in-memory and
      resets on UTC month rollover — note that a **server restart resets the
      in-memory monthly counter**, so frequent restarts could let spend exceed
      the intended monthly figure. Watch the `@director budget` command
      (`get_budget_stats`, `claude_provider.py:271`) day-one. If you need a
      hard cap across restarts, that is a known follow-up (persist spend) — log
      it, don't guess.
- [ ] **Era-clean:** no Imperial/Empire/Rebel/TIE in production strings
      (`active_era="clone_wars"`, B3 invariant). The era-cleanness tests in the
      suite cover this; confirm they pass.
- [ ] **`token_secret.key` durable** and ephemeral-fallback warning absent
      (Section 5.2).
- [ ] **`truststore` installed in venv** (Section 5.4) if the Director is live.
- [ ] **Backups scheduled** and one verified backup exists (Section 6.3).
- [ ] **Telnet decision applied** (LAN-only / off — Section 1.7 / 2.6).
- [ ] **DECISIONS NEEDED block at top resolved** (domain, path, telnet).

---

## 8. Deploy + smoke test

1. Start the edge first: `sc start cloudflared` (tunnel) or `caddy`/nginx
   service (proxy).
2. Start the server: `nssm start ParsecServer`. Confirm running:
   `sc query ParsecServer` → `STATE: RUNNING`.
3. **Portal loads over HTTPS:** from a device OFF your LAN (phone on cellular),
   open `https://parsec.example.com/` → Parsec portal renders, padlock valid.
   (Routes: `/` portal, `/play` client, `/chargen`, `/ws` websocket —
   `web_client.py:172-176`.) There is no dedicated `/health` endpoint; `/` is the
   liveness probe.
4. **WebSocket connects:** open `/play`, watch the browser devtools Network tab
   for the `wss://parsec.example.com/ws` upgrade → `101 Switching Protocols`. A
   connected client should receive the game stream.
5. **Login path:** create a **throwaway account** through `/chargen`
   (`POST /api/chargen/submit` / `create-character`, `api.py:333-336`), make a
   throwaway character, walk a few rooms. This exercises bcrypt account create
   (`database.py:1837`), HMAC token issue (`api.py:122-147`), and a DB write
   round-trip end to end.
6. **Throttle sanity (proxy path):** confirm rapid repeated chargen attempts get
   rate-limited per real client IP, proving `SWMUSH_TRUSTED_PROXIES` is wired
   (Section 2.5). If one external client never trips the limit, the proxy IP is
   collapsing the bucket — fix before opening up.
7. Delete the throwaway account/character (admin) once satisfied.

---

## 9. Rollback + monitoring

### Stop / restart
```
nssm stop ParsecServer       # stop the game server
nssm restart ParsecServer    # bounce it
sc stop cloudflared          # take the public endpoint down (tunnel)
```
To take the game offline fast without code: `sc stop cloudflared` removes public
reachability instantly while leaving the server (and DB) untouched.

### Logs
- Game server: `C:\SW_MUSH\logs\server.out.log` / `server.err.log` (NSSM
  redirection, Section 4.4). Default log level INFO (`main.py:42`); raise to
  DEBUG by editing the NSSM `--log-level DEBUG` parameter and restarting.
- Tunnel: `cloudflared` service logs (Event Viewer / its own log path).
- Proxy: Caddy/nginx access+error logs.

### Code rollback
One drop = one git branch; production runs from `C:\SW_MUSH` on a known commit.
To roll back code: `nssm stop ParsecServer`, `git -C C:\SW_MUSH checkout <good-commit>`
(or `git branch -f main <good-commit>` per the sole-dev model), reinstall deps if
they changed, `nssm start ParsecServer`. If the rollback involves the DB schema,
follow the restore procedure in `backup_restore_runbook_v1.md` first.

### Minimal uptime check
A tiny scheduled check that the public URL answers (e.g. a Task Scheduler job that
curls `https://parsec.example.com/` and emails/logs on non-200), or a free
external monitor (UptimeRobot/Cloudflare Health Checks) hitting `/`. Since `/` is
the liveness route and NSSM already auto-restarts a crashed process, the external
check mainly catches the case where the process is up but wedged, or the
tunnel/proxy is down.

---

## 10. Day-one operations

- **Watch the Director budget.** Run `@director budget` in-game (surfaces
  `get_budget_stats`, `claude_provider.py:271`). The hard guard is $18 (90% of
  $20) — at that point Director calls return empty and degrade gracefully. Note
  the restart-resets-the-monthly-counter caveat (Section 7) — if you restart the
  service a lot in one month, eyeball actual API spend in the Anthropic console,
  not just the in-game number.
- **Watch the credit economy.** Keep an eye on the credit faucets/sinks balance
  (the economy dashboard / `@director`-side telemetry). Faucets and sinks ship
  together by invariant, but real player behavior can still skew the curve —
  watch for runaway inflation/deflation in the first days.
- **Watch player reports.** Triage in-game bug/report channels and the QA blocker
  backlog (the QA campaign findings). Have the rollback (Section 9) and restore
  (`backup_restore_runbook_v1.md`) procedures one keystroke away.
- **Watch the logs** for the token-secret ephemeral-fallback warning, repeated
  crash-restarts (NSSM throttle kicking in), and DB busy/lock errors.
- **Backups:** confirm the daily `ParsecBackup` task actually produced a verified
  snapshot (check `C:\SW_MUSH\backups\` mtime + the `--verify` exit) — a backup
  job that silently stopped is worse than none.

---

## Appendix: gap → section map (from the hosting audit)

| Gap (severity) | Resolved in |
| --- | --- |
| TLS / HTTPS (blocker) | §1 (tunnel TLS at edge) / §2 (proxy + Let's Encrypt) |
| Public bind surface (blocker) | §0.2 (bind 127.0.0.1 or never forward) + §1.7/§2.6 (telnet) |
| Process supervision (blocker) | §4 (NSSM auto-restart + boot start) |
| Token-secret durability (high) | §5.2 |
| Prod config path (high) | §5.3 |
| DB backups + integrity (high) | §6 |
| Trusted-proxy IP wiring (high) | §2.5 / §5.1 |
| Telnet exposure (high) | §1.7 / §2.6 |
| DDoS / connection limits (nice) | edge limits at §1 (Cloudflare) / proxy §2 |
