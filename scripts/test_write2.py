"""
Prueba variantes del evento de escritura.
El termostato está en 25°C — escribimos 25.5 para detectar cuál funciona.
Confirmación: si 1_0_2 y 1_0_3 cambian a 25.5 = ÉXITO.
"""
import socketio
import time

ONNA_ID       = "1HPNi16"
WRITE_ADDR    = "1_0_2"
STATUS_ADDR   = "1_0_3"
WRITE_VALUE   = 25.5   # Desde 25.0 → detectamos el cambio

state = {}
sio   = socketio.Client(logger=False, engineio_logger=False)


@sio.on("SET_ADDRESS_VALUE_FROM_SERVER")
def on_address(data):
    addr = data.get("id")
    val  = data.get("value")
    prev = state.get(addr)
    state[addr] = val
    if addr in (WRITE_ADDR, STATUS_ADDR) and prev != val:
        t = time.strftime("%H:%M:%S")
        print(f"  {t}  [{addr}]  {prev} → {val}  <<<< CAMBIO")


@sio.on("connect")
def on_connect():
    print("[OK] Conectado\n")


sio.connect(
    f"http://192.168.10.3:4001?onnaId={ONNA_ID}",
    transports=["websocket"],
)
sio.sleep(5)
print(f"Estado inicial: 1_0_2={state.get('1_0_2','?')}  1_0_3={state.get('1_0_3','?')}\n")


def try_emit(label, event, payload):
    print(f">>> [{label}] emit '{event}' {payload}")
    sio.emit(event, payload)
    sio.sleep(8)
    changed = state.get(WRITE_ADDR) == WRITE_VALUE or state.get(STATUS_ADDR) == WRITE_VALUE
    result = "✓ ÉXITO" if changed else "✗ Sin cambio"
    print(f"    {result}\n")
    return changed


# Variante 1: formato básico (ya probado)
ok = try_emit("1", "SET_ADDRESS_VALUE", {"id": WRITE_ADDR, "value": WRITE_VALUE})

# Variante 2: con onnaId en el payload
if not ok:
    ok = try_emit("2", "SET_ADDRESS_VALUE",
                  {"id": WRITE_ADDR, "value": WRITE_VALUE, "onnaId": ONNA_ID})

# Variante 3: con type DPT
if not ok:
    ok = try_emit("3", "SET_ADDRESS_VALUE",
                  {"id": WRITE_ADDR, "value": WRITE_VALUE, "type": "9.001"})

# Variante 4: nombre de evento diferente
if not ok:
    ok = try_emit("4", "WRITE_ADDRESS_VALUE", {"id": WRITE_ADDR, "value": WRITE_VALUE})

# Variante 5: SET_VALUE
if not ok:
    ok = try_emit("5", "SET_VALUE", {"id": WRITE_ADDR, "value": WRITE_VALUE})

# Variante 6: address con slashes
if not ok:
    ok = try_emit("6", "SET_ADDRESS_VALUE", {"id": "1/0/2", "value": WRITE_VALUE})

print("=== Fin de pruebas ===")
if not ok:
    print("Ninguna variante funcionó — el servidor rechaza escrituras externas")
    print("Próximo paso: SSH al Pi para ver el código del servidor")

sio.disconnect()
