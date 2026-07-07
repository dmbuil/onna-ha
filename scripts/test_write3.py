"""
Prueba el flujo completo de la app: READ_CONFIGURATION primero, luego SET_ADDRESS_VALUE.
Mientras corre: usa la app del móvil para cambiar el termostato.
"""
import socketio
import time

ONNA_ID    = "ONNA_ID"
WRITE_ADDR = "1_0_2"
STATE_ADDR = "1_0_3"
WRITE_VAL  = 25.5   # asumiendo que el termostato está en 25.0

state     = {}
got_ack   = False
sio       = socketio.Client(logger=False, engineio_logger=False)


@sio.on("SET_ADDRESS_VALUE_FROM_SERVER")
def on_addr(data):
    addr = data.get("id")
    val  = data.get("value")
    prev = state.get(addr)
    state[addr] = val
    t = time.strftime("%H:%M:%S")
    if addr in (WRITE_ADDR, STATE_ADDR):
        marker = " <<<< CAMBIO" if prev != val else ""
        src = "(nuestra escritura?)" if marker else ""
        print(f"  {t}  [{addr}]  {prev} → {val}{marker}  {src}")
    elif prev != val and prev is not None:
        print(f"  {t}  [{addr}]  {prev} → {val}")


@sio.on("connect")
def on_connect():
    print("[OK] Conectado")


@sio.on("disconnect")
def on_disconnect():
    print("[!] Desconectado")


sio.connect(
    f"http://192.168.10.3:4001?onnaId={ONNA_ID}",
    transports=["websocket"],
)

# 1. Enviar READ_CONFIGURATION con ack (como hace la app)
print("\n>>> Enviando READ_CONFIGURATION...")
ack_data = {}

def on_rc_ack(*args):
    global got_ack
    got_ack = True
    ack_data['data'] = args
    print(f"    Ack recibido ({len(str(args))} chars)")

sio.emit("READ_CONFIGURATION", callback=on_rc_ack)

# Esperar el ack
for _ in range(50):  # hasta 5 s
    sio.sleep(0.1)
    if got_ack:
        break

print(f"    READ_CONFIGURATION ack: {'OK' if got_ack else 'timeout'}\n")

# 2. Esperar estado inicial (5 s más)
print("=== Estado inicial (5 s) ===")
sio.sleep(5)
print(f"  1_0_2 = {state.get(WRITE_ADDR, '?')}")
print(f"  1_0_3 = {state.get(STATE_ADDR, '?')}\n")

# 3. Escribir setpoint
print(f">>> AHORA: usa la app del móvil para cambiar el termostato")
print(f">>> Y simultáneamente enviamos: SET_ADDRESS_VALUE {WRITE_ADDR}={WRITE_VAL}")
sio.emit("SET_ADDRESS_VALUE", {"id": WRITE_ADDR, "value": WRITE_VAL})

# 4. Escuchar 30 s
print("\n=== 30 s escuchando ambos cambios ===")
sio.sleep(30)

print("\n=== Resultado ===")
print(f"  1_0_2 = {state.get(WRITE_ADDR, '?')}")
print(f"  1_0_3 = {state.get(STATE_ADDR, '?')}")

sio.disconnect()
