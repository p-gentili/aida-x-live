#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Paolo Gentili
"""AIDA-X hosted in Carla's engine, controllable over a Unix socket.

Commands (one per line, reply ends with a line "."):
  list                 all parameters with current values and ranges
  get SYM              current value of a parameter (symbol or Carla index)
  set SYM VAL          set parameter, replies with read-back value
  ui on|off            show/hide AIDA-X's own window (load models/IRs there)
  custom               dump plugin custom data (model / cab paths live here)
  load json|cabinet P  load an amp model (.json) or cab IR (.wav)
  save NAME            save model, cab and knobs as a preset
  recall NAME          load a preset
  presets              list presets
  quit                 stop
Client:  aida-x-ctl set BASS 3
Startup flags: --headless, --preset NAME, --model FILE, --cab FILE

Model/cab loading goes through a plugin-state round trip (save state, edit the
path entries, load it back). Carla only hands paths to AIDA-X through its state
restore; set_custom_data() with either atom#Path or Carla's own path type is
stored or dropped without the plugin ever seeing it.
"""
import os, sys, re, glob, socket, select, signal, tempfile
from xml.sax.saxutils import escape

sys.path.insert(0, "/usr/share/carla")
import carla_backend as cb

URI = "http://aidadsp.cc/plugins/aidadsp-bundle/rt-neural-loader"
SOCK = os.path.expanduser("~/.local/state/aida-x/carla.sock")
LV2_PATH = os.path.expanduser("~/.local/opt/AIDA-X") + ":" + os.environ.get(
    "LV2_PATH", os.path.expanduser("~/.lv2") + ":/usr/lib/lv2:/usr/local/lib/lv2")
PID = 0
PATCH_PREFIX = URI + "#"
STATE_DIR = os.path.dirname(SOCK)
PRESET_DIR = os.path.join(STATE_DIR, "presets")
os.makedirs(PRESET_DIR, exist_ok=True)
os.chdir(STATE_DIR)  # Carla writes a "<client>.tmp" dir of path symlinks into the CWD

def already_running():
    try:
        with socket.socket(socket.AF_UNIX) as probe:
            probe.connect(SOCK)
        return True
    except OSError:
        return False


# Two daemons would fight over the socket and the "AIDA-X" JACK name, leaving
# the one you hear and the one you control as different processes.
if already_running():
    sys.exit(f"aida-x-carla: already running ({SOCK} is live)")

host = cb.CarlaHostDLL("/usr/lib/carla/libcarla_standalone2.so", False)
host.set_engine_option(cb.ENGINE_OPTION_PATH_BINARIES, 0, "/usr/lib/carla")
host.set_engine_option(cb.ENGINE_OPTION_PATH_RESOURCES, 0, "/usr/lib/carla/resources")
host.set_engine_option(cb.ENGINE_OPTION_PROCESS_MODE, cb.ENGINE_PROCESS_MODE_MULTIPLE_CLIENTS, "")
host.set_engine_option(cb.ENGINE_OPTION_PLUGIN_PATH, cb.PLUGIN_LV2, LV2_PATH)
host.set_engine_option(cb.ENGINE_OPTION_OSC_ENABLED, 0, "")

if not host.engine_init("JACK", "Carla-AIDA-X"):
    sys.exit("engine_init failed: " + host.get_last_error())
if not host.add_plugin(cb.BINARY_NATIVE, cb.PLUGIN_LV2, "", "AIDA-X", URI, 0, None, 0):
    sys.exit("add_plugin failed: " + host.get_last_error())
host.set_active(PID, True)


def load_paths(paths):
    """paths: {"json"|"cabinet": file}. Applied via a state save/edit/load."""
    for k, v in paths.items():
        if k not in ("json", "cabinet"):
            raise ValueError(f"unknown property {k!r} (json | cabinet)")
        if not os.path.isfile(v):
            raise FileNotFoundError(v)
    fd, tmp = tempfile.mkstemp(suffix=".carxs", dir=STATE_DIR)
    os.close(fd)
    try:
        if not host.save_plugin_state(PID, tmp):
            raise RuntimeError(host.get_last_error())
        xml = open(tmp).read()
        for k, v in paths.items():
            xml, n = re.subn(rf"(#{k}</Key>\s*<Value>)[^<]*",
                             lambda m: m.group(1) + escape(v), xml)
            if n != 1:
                raise RuntimeError(f"no {k} entry in saved state")
        open(tmp, "w").write(xml)
        if not host.load_plugin_state(PID, tmp):
            raise RuntimeError(host.get_last_error())
    finally:
        os.unlink(tmp)


def absolutize_state(path):
    """Carla saves path properties as bare file names that point into its
    temporary "<client>.tmp" symlink folder, which is gone after a restart.
    Rewrite them to the real absolute paths so presets survive restarts."""
    links = {}
    for d in glob.glob(os.path.join(STATE_DIR, "Carla_*", "*")):
        for f in os.listdir(d):
            links.setdefault(f, os.path.realpath(os.path.join(d, f)))
    xml = open(path).read()

    def fix(m):
        v = m.group(2)
        if v.startswith("/") or v in ("", "default"):
            return m.group(0)
        if v not in links:
            raise RuntimeError(f"can't resolve {v!r} to a real path")
        return m.group(1) + escape(links[v])
    xml = re.sub(r"(#(?:json|cabinet)</Key>\s*<Value>)([^<]*)", fix, xml)
    open(path, "w").write(xml)


def preset_path(name):
    if "/" in name:
        return os.path.abspath(os.path.expanduser(name))
    return os.path.join(PRESET_DIR, name if name.endswith(".carxs") else name + ".carxs")


def recall(name):
    path = preset_path(name)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if not host.load_plugin_state(PID, path):
        raise RuntimeError(host.get_last_error())


argv = sys.argv[1:]
def flag(name):
    return os.path.expanduser(argv[argv.index(name) + 1]) if name in argv else None
if flag("--preset"):
    recall(flag("--preset"))
startup = {k: os.path.abspath(flag(f)) for f, k in (("--model", "json"), ("--cab", "cabinet")) if flag(f)}
if startup:
    load_paths(startup)
if "--headless" not in argv:
    host.show_custom_ui(PID, True)


def params():
    out = {}
    for i in range(host.get_parameter_count(PID)):
        info = host.get_parameter_info(PID, i)
        data = host.get_parameter_data(PID, i)
        out[i] = (info["symbol"] or info["name"], info, data)
    return out


def resolve(key):
    ps = params()
    if key.isdigit():
        return int(key)
    for i, (sym, info, _) in ps.items():
        if key.lower() in (sym.lower(), info["name"].lower()):
            return i
    raise KeyError(f"unknown parameter {key!r}")


def handle(line):
    a = line.split()
    if not a:
        return ""
    c = a[0].lower()
    if c == "list":
        rows = []
        for i, (sym, info, data) in params().items():
            r = host.get_parameter_ranges(PID, i)
            v = host.get_current_parameter_value(PID, i)
            kind = "out" if data["type"] == cb.PARAMETER_OUTPUT else "in"
            rows.append(f"{i:2d} {sym:14s} {v:10.3f}  [{r['min']:g}..{r['max']:g}] {kind}")
        return "\n".join(rows)
    if c == "get":
        i = resolve(a[1])
        return f"{params()[i][0]} = {host.get_current_parameter_value(PID, i):g}"
    if c == "set":
        i = resolve(a[1])
        r = host.get_parameter_ranges(PID, i)
        v = max(r["min"], min(r["max"], float(a[2])))
        host.set_parameter_value(PID, i, v)
        return f"{params()[i][0]} = {host.get_current_parameter_value(PID, i):g}"
    if c == "ui":
        host.show_custom_ui(PID, a[1:2] != ["off"])
        return "ok"
    if c == "custom":
        rows = []
        for j in range(host.get_custom_data_count(PID)):
            d = host.get_custom_data(PID, j)
            rows.append(f"{d['type']}  {d['key']}  {d['value'][:200]}")
        return "\n".join(rows) or "(none)"
    if c == "load":
        path = os.path.abspath(os.path.expanduser(line.split(None, 2)[2]))
        load_paths({a[1]: path})
        return f"{a[1]} = {path}"
    if c == "save":
        path = preset_path(line.split(None, 1)[1])
        if not host.save_plugin_state(PID, path):
            return "error: " + host.get_last_error()
        absolutize_state(path)
        return f"saved {path}"
    if c == "recall":
        recall(line.split(None, 1)[1])
        return "ok"
    if c == "presets":
        return "\n".join(sorted(f[:-6] for f in os.listdir(PRESET_DIR) if f.endswith(".carxs"))) or "(none)"
    if c == "quit":
        raise SystemExit
    return "unknown command"


os.makedirs(os.path.dirname(SOCK), exist_ok=True)
try:
    os.unlink(SOCK)
except FileNotFoundError:
    pass
srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
srv.bind(SOCK)
srv.listen(4)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
print("ready", flush=True)

try:
    while host.is_engine_running():
        r, _, _ = select.select([srv], [], [], 0.03)
        host.engine_idle()
        if r:
            conn, _ = srv.accept()
            with conn:
                conn.settimeout(2)
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                try:
                    reply = handle(buf.decode().strip())
                except SystemExit:
                    conn.sendall(b"bye\n.\n")
                    break
                except Exception as e:  # report, keep running
                    reply = f"error: {e}"
                conn.sendall((reply + "\n.\n").encode())
finally:
    host.remove_all_plugins()
    host.engine_close()
    os.unlink(SOCK)
