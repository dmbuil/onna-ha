"""
Escucha TODOS los eventos SET_ADDRESS_VALUE_FROM_SERVER.
Úsalo para observar qué pasa cuando alguien cambia el termostato físico.
"""
import json
import os
import socketio
import time

ONNA_ID  = "1HPNi16"
CONFIG   = os.path.join(os.path.dirname(__file__), "..", "out.onna.txt")
state    = {}
sio      = socketio.Client(logger=False, engineio_logger=False)

# Build id → name lookup from out.onna.txt
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


@sio.on("SET_ADDRESS_VALUE_FROM_SERVER")
def on_address(data):
    addr = data.get("id")
    val  = data.get("value")
    prev = state.get(addr)
    state[addr] = val
    t = time.strftime("%H:%M:%S")
    if prev is not None and prev != val:
        print(f"  {t}  CAMBIO  {_label(addr)}  {prev}  →  {val}")
    elif prev is None:
        print(f"  {t}  INIT    {_label(addr)}  {val}")


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
