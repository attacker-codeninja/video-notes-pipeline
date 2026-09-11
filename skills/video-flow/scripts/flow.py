#!/usr/bin/env python3
"""video-flow support script -- deterministic helpers the SKILL.md orchestrates
around: resolving a video/playlist/channel URL into an ordered, already-done-
filtered list of videos; creating/destroying a scratch working directory (a
RAM disk on macOS when available, a plain temp directory everywhere else, or
when explicitly requested); and tracking which video IDs have already
produced a final note. Does not touch video-perceive or video-summary -- it only calls
yt-dlp directly and manages its own tiny processed.log next to the delivered
notes.

Subcommands:
  list <source> [--order oldest|newest] [--count N|all] [--out DIR] [--force]
      Prints TAB-separated "id\ttitle\turl" lines, one per video to process,
      in the requested order, already-done ones filtered out (unless --force).
  workdir-create [--size-gb N] [--no-ramdisk]
      Creates a scratch working directory for one run and prints
      "<path>\t<kind>" where kind is "ramdisk" or "plain".
      - On macOS, without --no-ramdisk: tries to create/reuse a RAM disk
        (fast, and guarantees nothing touches the real disk while a video is
        being processed). Falls back to a plain temp directory if RAM disk
        creation fails for any reason (no macOS diskutil/hdiutil, insufficient
        RAM, etc.) -- this is optional acceleration, not a hard requirement.
      - Everywhere else, or with --no-ramdisk: a plain temp directory. Storage
        safety still holds either way -- video-flow deletes each video's
        working folder right after its note is delivered, so nothing
        accumulates regardless of which kind of scratch space is used.
  workdir-destroy <path> <kind>
      Tears down the scratch directory created by workdir-create -- ejects
      the RAM disk volume for "ramdisk", or removes the directory tree for
      "plain".
  mark-done <out-dir> -- <video-id>
      Appends video-id to <out-dir>/.video-flow-processed.log. The `--`
      before the id is required -- YouTube video IDs can start with a `-`,
      which argparse would otherwise read as a flag.
"""
from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VOLUME_NAME = "VideoFlowRAM"
MOUNT_PATH = Path(f"/Volumes/{VOLUME_NAME}")
LOG_NAME = ".video-flow-processed.log"
SEP = "\x1f"


def die(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(1)


def load_done_ids(out_dir: Path) -> set:
    log_path = out_dir / LOG_NAME
    if not log_path.exists():
        return set()
    return {line.strip() for line in log_path.read_text().splitlines() if line.strip()}


def cmd_list(args):
    out_dir = Path(args.out).expanduser().resolve()
    done_ids = set() if args.force else load_done_ids(out_dir)

    r = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--skip-download",
         "--print", f"%(id)s{SEP}%(title)s{SEP}%(webpage_url)s", args.source],
        capture_output=True, text=True,
    )
    entries = []
    for line in r.stdout.splitlines():
        parts = line.split(SEP)
        if len(parts) != 3 or not parts[2]:
            continue
        entries.append({"id": parts[0] or None, "title": parts[1] or "", "url": parts[2]})
    if not entries:
        die(f"yt-dlp could not resolve any video from source: {args.source}\n{r.stderr[-800:]}")

    is_single = (len(entries) == 1 and entries[0]["id"] and args.source.strip() == entries[0]["url"].strip())
    # yt-dlp --flat-playlist lists a real playlist/channel newest-first.
    if not is_single and args.order == "oldest":
        entries.reverse()

    pending = [e for e in entries if e["id"] not in done_ids]

    if not is_single and args.count != "all":
        pending = pending[: int(args.count)]

    for e in pending:
        print(f"{e['id']}\t{e['title']}\t{e['url']}")


def _total_ram_gb() -> float:
    out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
    return int(out.stdout.strip()) / (1024 ** 3)


def _create_ramdisk(size_gb: float | None) -> Path:
    if MOUNT_PATH.is_dir() and MOUNT_PATH.is_mount():
        return MOUNT_PATH

    resolved_size = size_gb if size_gb else max(2, min(6, _total_ram_gb() * 0.25))
    sectors = int(resolved_size * 2097152)  # 1 GB = 2097152 x 512-byte sectors
    attach = subprocess.run(["hdiutil", "attach", "-nomount", f"ram://{sectors}"],
                             capture_output=True, text=True, check=True)
    device = attach.stdout.strip().splitlines()[-1].split()[0]
    subprocess.run(["diskutil", "erasevolume", "APFS", VOLUME_NAME, device], check=True,
                    capture_output=True, text=True)
    return MOUNT_PATH


def _destroy_ramdisk():
    if MOUNT_PATH.is_dir() and MOUNT_PATH.is_mount():
        subprocess.run(["diskutil", "eject", str(MOUNT_PATH)], capture_output=True, text=True)


def cmd_workdir_create(args):
    if not args.no_ramdisk and platform.system() == "Darwin":
        try:
            path = _create_ramdisk(args.size_gb)
            print(f"{path}\tramdisk")
            return
        except Exception as e:
            print(f"[video-flow] RAM disk unavailable ({e}); using a plain scratch "
                  f"directory instead", file=sys.stderr)

    workdir = Path(tempfile.mkdtemp(prefix="video-flow-"))
    print(f"{workdir}\tplain")


def cmd_workdir_destroy(args):
    path = Path(args.path)
    if args.kind == "ramdisk":
        _destroy_ramdisk()
    else:
        shutil.rmtree(path, ignore_errors=True)


def cmd_mark_done(args):
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / LOG_NAME
    with log_path.open("a") as f:
        f.write(args.video_id + "\n")


def main():
    p = argparse.ArgumentParser(description="video-flow deterministic helpers")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("source")
    p_list.add_argument("--order", choices=["oldest", "newest"], default="oldest")
    p_list.add_argument("--count", default="1")
    p_list.add_argument("--out", default=".")
    p_list.add_argument("--force", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_create = sub.add_parser("workdir-create")
    p_create.add_argument("--size-gb", type=float, default=None)
    p_create.add_argument("--no-ramdisk", action="store_true",
                           help="skip the RAM disk even on macOS and use a plain temp directory")
    p_create.set_defaults(func=cmd_workdir_create)

    p_destroy = sub.add_parser("workdir-destroy")
    p_destroy.add_argument("path")
    p_destroy.add_argument("kind", choices=["ramdisk", "plain"])
    p_destroy.set_defaults(func=cmd_workdir_destroy)

    p_mark = sub.add_parser("mark-done")
    p_mark.add_argument("out_dir")
    p_mark.add_argument("video_id")
    p_mark.set_defaults(func=cmd_mark_done)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
