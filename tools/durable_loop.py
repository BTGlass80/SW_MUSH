#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/durable_loop.py — disk-persisted scheduler for the autonomous dev loop.

WHY: Claude Code's in-session CronCreate timers are session-only here (they die
when the app closes), so an unattended loop stalls across a restart / compute gap.
This wraps the OS-native, DISK-PERSISTED **Windows Task Scheduler** (the right tool
for the job — don't reinvent a daemon) so a scheduled "resume" fires even after the
app closes, the box reboots, or a usage-limit window ends.

WHAT each fire does: launches Claude Code HEADLESSLY (`claude -p`, reading a resume
prompt from stdin) in a chosen worktree, logging output to a timestamped file. The
prompt tells that fresh session to read the self-contained HANDOFF/RESUME doc and do
the next bounded chunk of work, then stop. Auth is inherited from the user-scope
ANTHROPIC_API_KEY (verified present on this box) — no secret is written by this tool.

Task Scheduler gives us, natively:
  * durability across restarts (it persists tasks to disk and the OS keeps it alive);
  * `MultipleInstancesPolicy=IgnoreNew` — a fire that lands while a prior run is still
    going is SKIPPED, so two claude sessions never fight over git;
  * `StartWhenAvailable` — a fire missed while the box was off/asleep runs as soon as
    it is back (covers the compute-gap case);
  * `ExecutionTimeLimit` — a hung run is killed so it can't block the loop forever.

USE (Windows only; run as the logged-on dev user — no admin needed):
  python tools/durable_loop.py arm --every 20 --workdir C:/SW_MUSH_night
  python tools/durable_loop.py arm --in 300                # one-shot, 300s from now
  python tools/durable_loop.py arm --at "2026-06-14 22:30" # one-shot at a wall-clock time
  python tools/durable_loop.py list
  python tools/durable_loop.py status                      # tail the latest run log
  python tools/durable_loop.py disarm                      # stop + remove the task
Add --dry-run to `arm` to print the launcher + task XML without registering.
Add --test-fire to `arm` to schedule a BENIGN marker-writing run (no claude) — used
to self-test the scheduler plumbing end-to-end.

SAFETY: the default permission mode is `--dangerously-skip-permissions` (the loop
must run git/pytest/edits unattended). Only arm this on a repo + worktree you trust,
and `disarm` it when the loop's purpose is done.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_NAME = "SWMUSH-DurableLoop"
DEFAULT_MODEL = "opus"
_HOME = Path(os.environ.get("USERPROFILE") or Path.home())
STATE_ROOT = _HOME / ".claude" / "durable_loop"
_DEFAULT_HANDOFF = "docs/design/HANDOFF_overnight_main_dev_2026-06-14.md"


# ── pure builders (unit-tested) ──────────────────────────────────────────────

def detect_claude() -> str:
    """Best-effort locate claude.exe (the headless CLI)."""
    cand = [
        _HOME / ".local" / "bin" / "claude.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "claude" / "claude.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Claude Code" / "bin" / "claude.exe",
    ]
    for c in cand:
        if c.is_file():
            return str(c)
    # fall back to PATH resolution at run time
    return "claude"


def default_prompt(workdir: str, handoff: str = _DEFAULT_HANDOFF) -> str:
    """The resume prompt a scheduled fire feeds to `claude -p`."""
    return (
        "AUTONOMOUS SW_MUSH dev loop — scheduled durable fire (you are a fresh "
        "headless session; there may be no prior context). STEP 1: read "
        f"{handoff} and C:\\Users\\btgla\\.claude\\projects\\c--SW-MUSH\\"
        "RESUME_unattended_2026-06-14.md in full. STEP 2: run the EACH WAKE loop — "
        f"work ONLY in this worktree ({workdir}); check git state, fetch origin, and "
        "do the NEXT collision-free drop from the next-up queue: implement with "
        "targeted tests green, run the full suite as a FOREGROUND-BLOCKING gate "
        "(timeout ~9 min; NEVER background-and-wait-for-a-notification), then "
        "auto-merge to main via fetch+merge+push. Update CHANGELOG.md + TODO.json in "
        "the same commit; add a per-drop test file. If a drop is mid-flight, finish "
        "it first. STOP after one drop (or if a human is clearly active, or the queue "
        "is exhausted) — the next scheduled fire continues. NEVER touch other "
        "worktrees / sessions' trees."
    )


def perm_flag(mode: str) -> str:
    if mode == "bypass":
        return "--dangerously-skip-permissions"
    if mode == "accept-edits":
        return "--permission-mode acceptEdits"
    raise ValueError(f"unknown perm mode {mode!r} (use 'bypass' or 'accept-edits')")


def build_launcher(workdir: str, claude_exe: str, prompt_file: str, log_dir: str,
                   model: str, perm_mode: str, raw_action: str | None = None) -> str:
    """The .cmd Task Scheduler runs each fire. Generated — do not hand-edit."""
    head = (
        "@echo off\r\n"
        "REM SW_MUSH durable autonomous-loop launcher (generated by "
        "tools/durable_loop.py). Do not edit by hand.\r\n"
        "setlocal\r\n"
        # Use the flat-rate Claude subscription, NOT the metered API key.
        # Brian 2026-06-15: the user-scope ANTHROPIC_API_KEY billed pay-per-token
        # Opus (~$31/day) AND its prepaid balance hit $0 ("credit balance too
        # low") which killed every headless fire. Clearing it here makes
        # `claude -p` fall back to the logged-in Max subscription (verified
        # working headless) — flat rate, no per-token fees.
        'set "ANTHROPIC_API_KEY="\r\n'
        # sortable, locale-independent timestamp (yyyyMMdd_HHmmss)
        "for /f %%I in ('powershell -NoProfile -Command "
        "\"Get-Date -Format yyyyMMdd_HHmmss\"') do set \"TS=%%I\"\r\n"
        f'cd /d "{workdir}"\r\n'
    )
    if raw_action is not None:
        body = f'{raw_action} > "{log_dir}\\run_%TS%.log" 2>&1\r\n'
    else:
        body = (
            f'type "{prompt_file}" | "{claude_exe}" -p {perm_flag(perm_mode)} '
            f'--model {model} > "{log_dir}\\run_%TS%.log" 2>&1\r\n'
        )
    return head + body + "endlocal\r\n"


def _iso(dt: _dt.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_task_xml(launcher_path: str, *, start_dt: _dt.datetime,
                   every_minutes: int | None = None, description: str = "",
                   exec_time_limit: str = "PT2H") -> str:
    """Windows Task Scheduler v1.2 XML. Recurring if every_minutes is set, else one-shot."""
    if every_minutes is not None:
        repetition = (
            "      <Repetition>\n"
            f"        <Interval>PT{int(every_minutes)}M</Interval>\n"
            "        <StopAtDurationEnd>false</StopAtDurationEnd>\n"
            "      </Repetition>\n"
        )
    else:
        repetition = ""
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        "    <Author>SW_MUSH durable_loop</Author>\n"
        f"    <Description>{description}</Description>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        "    <TimeTrigger>\n"
        f"      <StartBoundary>{_iso(start_dt)}</StartBoundary>\n"
        f"{repetition}"
        "      <Enabled>true</Enabled>\n"
        "    </TimeTrigger>\n"
        "  </Triggers>\n"
        "  <Principals>\n"
        '    <Principal id="Author">\n'
        "      <LogonType>InteractiveToken</LogonType>\n"
        "      <RunLevel>LeastPrivilege</RunLevel>\n"
        "    </Principal>\n"
        "  </Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <StartWhenAvailable>true</StartWhenAvailable>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <AllowHardTerminate>true</AllowHardTerminate>\n"
        f"    <ExecutionTimeLimit>{exec_time_limit}</ExecutionTimeLimit>\n"
        "    <Enabled>true</Enabled>\n"
        "  </Settings>\n"
        '  <Actions Context="Author">\n'
        "    <Exec>\n"
        "      <Command>cmd.exe</Command>\n"
        f'      <Arguments>/c "{launcher_path}"</Arguments>\n'
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


# ── CLI integration ──────────────────────────────────────────────────────────

def _task_dir(name: str) -> Path:
    return STATE_ROOT / name


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def cmd_arm(args) -> int:
    # resolve schedule
    now = _dt.datetime.now()
    every = None
    if args.every is not None:
        every = args.every
        start = now + _dt.timedelta(seconds=30)  # first fire ~30s out
    elif args.in_seconds is not None:
        start = now + _dt.timedelta(seconds=args.in_seconds)
    elif args.at is not None:
        try:
            start = _dt.datetime.strptime(args.at, "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"error: --at must be 'YYYY-MM-DD HH:MM' (got {args.at!r})", file=sys.stderr)
            return 2
    else:
        print("error: provide one of --every <min>, --in <seconds>, --at '<YYYY-MM-DD HH:MM>'",
              file=sys.stderr)
        return 2

    workdir = str(Path(args.workdir).resolve())
    claude_exe = args.claude or detect_claude()
    tdir = _task_dir(args.name)
    log_dir = tdir / "logs"
    prompt_file = tdir / "prompt.txt"
    launcher = tdir / "launcher.cmd"
    xml_file = tdir / "task.xml"

    prompt = args.prompt if args.prompt else (
        Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file
        else default_prompt(workdir))

    raw_action = None
    if args.test_fire:
        raw_action = 'echo durable_loop test fire %TS% & echo OK'

    launcher_text = build_launcher(workdir, claude_exe, str(prompt_file), str(log_dir),
                                   args.model, args.perm, raw_action=raw_action)
    desc = (f"SW_MUSH durable autonomous dev loop ({'every '+str(every)+'m' if every else 'one-shot'}); "
            f"workdir {workdir}; model {args.model}")
    xml_text = build_task_xml(str(launcher), start_dt=start, every_minutes=every, description=desc)

    if args.dry_run:
        print(f"# would register task {args.name!r} starting {_iso(start)}"
              f"{' every '+str(every)+'m' if every else ' (one-shot)'}\n")
        print("=== launcher.cmd ===\n" + launcher_text)
        print("=== task.xml ===\n" + xml_text)
        return 0

    if os.name != "nt":
        print("error: registering uses Windows Task Scheduler (Windows only); "
              "use --dry-run to inspect on other platforms.", file=sys.stderr)
        return 2

    # write state, register
    log_dir.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")
    launcher.write_text(launcher_text, encoding="utf-8", newline="")
    xml_file.write_text(xml_text, encoding="utf-16")  # schtasks expects UTF-16 task XML

    res = _run(["schtasks", "/create", "/tn", args.name, "/xml", str(xml_file), "/f"])
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    if res.returncode != 0:
        return res.returncode
    print(f"\narmed: {args.name}  (first fire {_iso(start)}"
          f"{', every '+str(every)+'m' if every else ', one-shot'})")
    print(f"  launcher: {launcher}\n  logs:     {log_dir}")
    print(f"  disarm with:  python tools/durable_loop.py disarm --name {args.name}")
    return 0


def cmd_list(args) -> int:
    res = _run(["schtasks", "/query", "/tn", args.name, "/v", "/fo", "LIST"])
    if res.returncode != 0:
        print(f"(no task named {args.name!r} registered)")
        return 0
    # show the lines that matter
    for line in res.stdout.splitlines():
        if any(k in line for k in ("TaskName:", "Status:", "Next Run Time:", "Last Run Time:",
                                   "Last Result:", "Schedule:", "Repeat:")):
            print(line.strip())
    return 0


def cmd_disarm(args) -> int:
    res = _run(["schtasks", "/delete", "/tn", args.name, "/f"])
    sys.stdout.write(res.stdout)
    sys.stderr.write(res.stderr)
    return res.returncode


def cmd_status(args) -> int:
    log_dir = _task_dir(args.name) / "logs"
    logs = (sorted(log_dir.glob("run_*.log"), key=lambda p: p.stat().st_mtime)
            if log_dir.is_dir() else [])
    if not logs:
        print(f"(no run logs yet under {log_dir})")
        return 0
    latest = logs[-1]
    print(f"=== latest run log: {latest.name} ===")
    text = latest.read_text(encoding="utf-8", errors="replace")
    print("\n".join(text.splitlines()[-args.tail:]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Disk-persisted scheduler for the autonomous dev loop "
                                            "(Windows Task Scheduler + headless claude).")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("arm", help="register a durable scheduled resume")
    g = a.add_mutually_exclusive_group()
    g.add_argument("--every", type=int, metavar="MIN", help="recurring: fire every MIN minutes")
    g.add_argument("--in", dest="in_seconds", type=int, metavar="SEC", help="one-shot: fire SEC seconds from now")
    g.add_argument("--at", metavar="'YYYY-MM-DD HH:MM'", help="one-shot: fire at a wall-clock time")
    a.add_argument("--name", default=DEFAULT_NAME)
    a.add_argument("--workdir", default="C:/SW_MUSH_night", help="worktree the fire runs in")
    a.add_argument("--model", default=DEFAULT_MODEL)
    a.add_argument("--claude", default=None, help="path to claude.exe (auto-detected if omitted)")
    a.add_argument("--perm", choices=["bypass", "accept-edits"], default="bypass",
                   help="bypass=--dangerously-skip-permissions (default; needed for unattended git/tests)")
    a.add_argument("--prompt", default=None, help="inline resume prompt (overrides default)")
    a.add_argument("--prompt-file", default=None, help="read the resume prompt from a file")
    a.add_argument("--dry-run", action="store_true", help="print launcher + XML, do not register")
    a.add_argument("--test-fire", action="store_true",
                   help="benign marker run instead of claude (self-test the plumbing)")
    a.set_defaults(func=cmd_arm)

    for name, fn, helptext in [("list", cmd_list, "show the registered task"),
                               ("disarm", cmd_disarm, "stop + remove the task"),
                               ("status", cmd_status, "tail the latest run log")]:
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--name", default=DEFAULT_NAME)
        if name == "status":
            s.add_argument("--tail", type=int, default=30)
        s.set_defaults(func=fn)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
