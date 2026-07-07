"""
Prueba de escritura usando python-socketio v4 (compatible con socket.io v2 / EIO=3).
Escribe 24.0°C en 1_0_2 (Salón+Cocina consigna) y observa 1_0_3 (estado).
"""
import socketio
import time

ONNA_ID = "ONNA_ID"

SETPOINT_ADDR  = "1_0_2"   # consigna (write)
SETPOINT_STATE = "1_0_3"   # consigna estado (readOnInit=true)
REAL_TEMP      = "1_0_4"   # temp real
ONOFF_STATE    = "1_0_1"   # ON/OFF estado

WRITE_VALUE = 24.0

state = {}
sio = socketio.Client(logger=True, engineio_logger=False)


@sio.on("SET_ADDRESS_VALUE_FROM_SERVER")
def on_address(data):
    addr = data.get("id")
    val  = data.get("value")
    prev = state.get(addr)
    state[addr] = val
    t = time.strftime("%H:%M:%S")
    labels = {
        SETPOINT_ADDR:  "consigna write",
        SETPOINT_STATE: "consigna estado",
        REAL_TEMP:      "temp real",
        ONOFF_STATE:    "ON/OFF estado",
        "0_5_3":        "potencia (W)",
    }
    if addr in labels or (prev is not None and prev != val):
        marker = " <CAMBIO" if prev is not None and prev != val else ""
        print(f"  {t} [{addr}] {labels.get(addr, addr)}: {val}{marker}")


@sio.on("connect")
def on_connect():
    print(f"[SIO] Conectado")


@sio.on("disconnect")
def on_disconnect():
    print(f"[SIO] Desconectado")


url = f"http://192.168.10.3:4001"
query_params = f"onnaId={ONNA_ID}"

print(f"Conectando a {url}?{query_params}\n")
sio.connect(
    f"{url}?{query_params}",
    transports=["websocket"],
    headers={},
)

# Capturar estado inicial (8 s)
print("\n=== Estado inicial (8 s) ===")
sio.sleep(8)

print(f"\nConsigna estado ({SETPOINT_STATE}): {state.get(SETPOINT_STATE, '?')} °C")
print(f"Temp real       ({REAL_TEMP}): {state.get(REAL_TEMP, '?')} °C")
print(f"ON/OFF estado   ({ONOFF_STATE}): {state.get(ONOFF_STATE, '?')}")

# Escribir setpoint
print(f"\n>>> emit SET_ADDRESS_VALUE {SETPOINT_ADDR} = {WRITE_VALUE}")
sio.emit("SET_ADDRESS_VALUE", {"id": SETPOINT_ADDR, "value": WRITE_VALUE})
print(f">>> Enviado. Mira el termostato físico del Salón (esperado: {WRITE_VALUE}°C)")

# Escuchar 20 s
print("\n=== 20 s post-escritura ===")
sio.sleep(20)

print("\n=== Resultado ===")
final = state.get(SETPOINT_STATE)
if final == WRITE_VALUE:
    print(f"✓ CONFIRMADO en {SETPOINT_STATE}: {WRITE_VALUE}°C")
else:
    print(f"Sin cambio en {SETPOINT_STATE} (valor: {final})")
    print(f"Revisa termostato físico: ¿muestra {WRITE_VALUE}°C?")

sio.disconnect()
