"""
Test SET_ADDRESS_VALUE write usando el flujo real de la app:
1. Conectar → READ_CONFIGURATION (dispara readOnInit broadcasts)
2. Capturar estado inicial (consigna actual de 1_0_2/1_0_3)
3. Escribir 24.0°C en 1_0_2
4. Esperar feedback en 1_0_3
"""
import asyncio
import json
import time
import websockets

HOST      = "192.168.10.3"
PORT      = 4001
ONNA_ID   = "ONNA_ID"

WRITE_ADDR  = "1_0_2"
STATUS_ADDR = "1_0_3"
REAL_ADDR   = "1_0_4"
ONOFF_ADDR  = "1_0_1"

WRITE_VALUE = 24.0

state   = {}
ws_ref  = None   # shared for keepalive task


async def keepalive(ws):
    """Respond to EIO pings (period ~10 s, timeout 5 s)."""
    while True:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            if msg == "2":
                await ws.send("3")
            else:
                # Put message back — not possible with asyncio; use queue instead
                pass
        except asyncio.TimeoutError:
            pass
        except Exception:
            break


async def run():
    url = (
        f"ws://{HOST}:{PORT}/socket.io/"
        f"?EIO=3&transport=websocket&onnaId={ONNA_ID}"
    )
    print(f"Conectando...\n")

    # Use a queue to decouple the recv loop from business logic
    queue: asyncio.Queue = asyncio.Queue()

    async with websockets.connect(url) as ws:
        # --- EIO open ---
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        eio = json.loads(msg[1:])
        print(f"[HS] SID={eio['sid']}  pingInterval={eio['pingInterval']}ms  pingTimeout={eio['pingTimeout']}ms")

        # Wait for namespace connect (server sends "40" automatically)
        frame = await asyncio.wait_for(ws.recv(), timeout=5)
        print(f"[HS] namespace: {frame!r}")

        # --- Receiver task: puts all frames on queue, handles pings inline ---
        async def receiver():
            while True:
                try:
                    msg = await ws.recv()
                except Exception as e:
                    await queue.put(("CLOSE", str(e)))
                    return
                if msg == "2":
                    await ws.send("3")
                else:
                    await queue.put(("MSG", msg))

        recv_task = asyncio.create_task(receiver())

        # --- READ_CONFIGURATION to trigger readOnInit broadcasts ---
        rc_frame = '421["READ_CONFIGURATION"]'
        print(f"\n>>> Enviando READ_CONFIGURATION: {rc_frame}")
        await ws.send(rc_frame)

        # --- Capture state for 10 s ---
        print("\n=== Estado inicial (10 s) ===")
        deadline = time.time() + 10
        while time.time() < deadline:
            remaining = deadline - time.time()
            try:
                kind, msg = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if kind == "CLOSE":
                print(f"  [CONEXIÓN CERRADA] {msg}")
                recv_task.cancel()
                return
            if msg.startswith("431"):
                # Ack response to READ_CONFIGURATION
                try:
                    payload = json.loads(msg[3:])
                    print(f"  [READ_CONFIGURATION ack] recibido ({len(str(payload))} chars)")
                    # Extract current values from ack if present
                    if isinstance(payload, list) and len(payload) > 0:
                        data = payload[0]
                        if isinstance(data, dict) and "addresses" in data:
                            for addr_obj in data["addresses"]:
                                aid = addr_obj.get("id")
                                val = addr_obj.get("value")
                                if val is not None:
                                    state[aid] = val
                except Exception as e:
                    print(f"  [ack parse error] {e}")
            elif msg.startswith("42"):
                try:
                    data = json.loads(msg[2:])
                except Exception:
                    continue
                if len(data) == 2 and data[0] == "SET_ADDRESS_VALUE_FROM_SERVER":
                    addr = data[1]["id"]
                    val  = data[1]["value"]
                    state[addr] = val
                    if addr in (WRITE_ADDR, STATUS_ADDR, REAL_ADDR, ONOFF_ADDR):
                        labels = {
                            WRITE_ADDR:  "consigna write",
                            STATUS_ADDR: "consigna estado",
                            REAL_ADDR:   "temp real",
                            ONOFF_ADDR:  "ON/OFF estado",
                        }
                        print(f"  [{addr}] {labels.get(addr, addr)}: {val}")

        print(f"\nEstado actual Salón+Cocina:")
        print(f"  ON/OFF estado  ({ONOFF_ADDR}): {state.get(ONOFF_ADDR, '?')}")
        print(f"  Temp real      ({REAL_ADDR}): {state.get(REAL_ADDR, '?')} °C")
        print(f"  Consigna estado({STATUS_ADDR}): {state.get(STATUS_ADDR, '?')} °C")
        print(f"  Consigna write ({WRITE_ADDR}): {state.get(WRITE_ADDR, '?')} °C")

        # --- Escribir nuevo setpoint ---
        frame_write = '42' + json.dumps(["SET_ADDRESS_VALUE", {"id": WRITE_ADDR, "value": WRITE_VALUE}])
        print(f"\n>>> ENVIANDO: {frame_write}")
        await ws.send(frame_write)
        print(f">>> ¡Mira el termostato físico del Salón ahora! (esperado: {WRITE_VALUE}°C)\n")

        # --- Escuchar 30 s post-escritura ---
        print("=== 30 s post-escritura ===")
        deadline = time.time() + 30
        while time.time() < deadline:
            remaining = deadline - time.time()
            try:
                kind, msg = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if kind == "CLOSE":
                print(f"  [CONEXIÓN CERRADA] {msg}")
                break
            if msg.startswith("42"):
                try:
                    data = json.loads(msg[2:])
                except Exception:
                    continue
                if len(data) == 2 and data[0] == "SET_ADDRESS_VALUE_FROM_SERVER":
                    addr = data[1]["id"]
                    val  = data[1]["value"]
                    prev = state.get(addr)
                    marker = " <<<< CAMBIO" if prev is not None and prev != val else ""
                    state[addr] = val
                    t = time.strftime("%H:%M:%S")
                    if addr in (WRITE_ADDR, STATUS_ADDR, REAL_ADDR, ONOFF_ADDR) or marker:
                        print(f"  {t} [{addr}]: {val}{marker}")
            else:
                t = time.strftime("%H:%M:%S")
                print(f"  {t} [RAW] {msg!r}")

        recv_task.cancel()

        # --- Resultado ---
        print("\n=== Resultado ===")
        final = state.get(STATUS_ADDR)
        if final == WRITE_VALUE:
            print(f"✓ ÉXITO: {STATUS_ADDR} confirmó {WRITE_VALUE}°C")
        elif final is not None:
            print(f"~ {STATUS_ADDR} reporta {final}°C (enviamos {WRITE_VALUE}°C)")
        else:
            print(f"Sin feedback en {STATUS_ADDR}")
            print(f"Revisa el termostato físico: ¿muestra {WRITE_VALUE}°C?")


asyncio.run(run())
