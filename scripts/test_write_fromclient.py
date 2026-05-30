"""
Prueba con el evento correcto: SET_ADDRESS_VALUE_FROM_CLIENT
Encontrado en el bundle de la app iOS (main.jsbundle).
Escribe 25.5°C en 1_0_2. Confirma si 1_0_2 y 1_0_3 cambian.
"""
import socketio
import time

ONNA_ID    = "1HPNi16"
WRITE_ADDR = "1_0_2"
STATE_ADDR = "1_0_3"
WRITE_VAL  = 25.5   # distinto de 25.0 actual

state = {}
sio   = socketio.Client(logger=False, engineio_logger=False)


@sio.on("SET_ADDRESS_VALUE_FROM_SERVER")
def on_addr(data):
    addr = data.get("id")
    val  = data.get("value")
    prev = state.get(addr)
    state[addr] = val
    if addr in (WRITE_ADDR, STATE_ADDR) or (prev is not None and prev != val):
        t = time.strftime("%H:%M:%S")
        marker = " <<<< CAMBIO" if prev != val else ""
        print(f"  {t}  [{addr}]  {prev} → {val}{marker}")


@sio.on("connect")
def on_connect():
    print("[OK] Conectado\n")


sio.connect(
    f"http://192.168.10.3:4001?onnaId={ONNA_ID}",
    transports=["websocket"],
)

# Estado inicial
sio.sleep(5)
print(f"Estado: 1_0_2={state.get('1_0_2','?')}  1_0_3={state.get('1_0_3','?')}\n")

# --- Escritura con el evento correcto ---
print(f">>> emit 'SET_ADDRESS_VALUE_FROM_CLIENT'  {WRITE_ADDR} = {WRITE_VAL}")
sio.emit("SET_ADDRESS_VALUE_FROM_CLIENT", {"id": WRITE_ADDR, "value": WRITE_VAL})
print(">>> Mira el termostato físico del Salón\n")

sio.sleep(20)

print(f"\nResultado:  1_0_2={state.get('1_0_2','?')}  1_0_3={state.get('1_0_3','?')}")
sio.disconnect()
