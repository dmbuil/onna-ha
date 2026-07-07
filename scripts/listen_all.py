"""
Escucha TODOS los eventos SET_ADDRESS_VALUE_FROM_SERVER.
Cada dirección KNX se imprime en un color diferente para identificar
fácilmente los telegramas del mismo origen.
"""
import json
import os
import socketio
import time

ONNA_ID  = "ONNA_ID"
CONFIG   = os.path.join(os.path.dirname(__file__), "..", "out.onna.txt")
state    = {}
sio      = socketio.Client(logger=False, engineio_logger=False)

# ---------------------------------------------------------------------------
# Colour palette — 16 visually distinct colours from the ANSI 256-colour set,
# spread evenly around the hue wheel and bright enough for dark terminals.
# ---------------------------------------------------------------------------
_PALETTE = [
    196,  # red
    202,  # orange
    226,  # yellow
    190,  # yellow-green
    46,   # bright green
    48,   # sea green
    51,   # cyan
    45,   # sky blue
    27,   # bright blue
    57,   # indigo
    93,   # purple
    129,  # violet
    201,  # magenta
    213,  # pink
    208,  # red-orange
    214,  # gold
]
_RESET = "\033[0m"


def _color(addr: str) -> str:
    """Return an ANSI escape sequence for addr — deterministic, same across runs."""
    idx = sum(ord(c) for c in addr) % len(_PALETTE)
    return f"\033[1;38;5;{_PALETTE[idx]}m"


# ---------------------------------------------------------------------------
# Name lookup from out.onna.txt
# ---------------------------------------------------------------------------
_names: dict[str, str] = {}
try:
    with open(CONFIG) as f:
        _data = json.load(f)
    for addr in _data.get("addresses", []):
        if isinstance(addr, dict) and "id" in addr:
            _names[addr["id"]] = addr.get("name", addr["id"])
except Exception:
    pass


def _label(addr: str) -> str:
    name = _names.get(addr, "")
    return f"[{addr:<8}]  {name:<45}" if name else f"[{addr:<8}]  {'':45}"


# ---------------------------------------------------------------------------
# Socket.IO handlers
# ---------------------------------------------------------------------------

@sio.on("SET_ADDRESS_VALUE_FROM_SERVER")
def on_address(data):
    addr = data.get("id")
    val  = data.get("value")
    prev = state.get(addr)
    state[addr] = val
    t   = time.strftime("%H:%M:%S")
    col = _color(addr)
    if prev is not None and prev != val:
        print(f"{col}  {t}  CAMBIO  {_label(addr)}  {prev}  →  {val}{_RESET}")
    elif prev is None:
        print(f"{col}  {t}  INIT    {_label(addr)}  {val}{_RESET}")


@sio.on("connect")
def on_connect():
    print("[OK] Conectado\n")


@sio.on("disconnect")
def on_disconnect():
    print("\n[!] Desconectado")


sio.connect(
    f"http://192.168.10.3:4001?onnaId={ONNA_ID}",
    transports=["websocket"],
)

print("Escuchando... (Ctrl+C para parar)\n")
try:
    sio.wait()
except KeyboardInterrupt:
    pass

sio.disconnect()
