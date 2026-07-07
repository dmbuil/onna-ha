"""
Diagnostic script: connect to Onna, request full state, and report
which entity addresses are reporting data vs. silent.

Usage: python3 scripts/diagnose_entities.py
"""
import asyncio
import json
import sys
import os

# Inline the address maps to avoid importing the full HA component tree
SENSOR_ADDRESSES = {
    "0_5_3":  ("Potencia",               "W"),
    "0_5_2":  ("Tensión",                "V"),
    "0_5_4":  ("Intensidad",             "mA"),
    "0_5_5":  ("Energía consumida",      "kWh"),
    "0_5_6":  ("Caudal Agua Fría",       "L/h"),
    "0_5_7":  ("Agua Fría consumida",    "m³"),
    "0_5_8":  ("Caudal Agua Caliente",   "L/h"),
    "0_5_9":  ("Agua Caliente consumida","m³"),
    "0_5_10": ("Caudal Agua Suelo",      "m³/h"),
    "0_5_11": ("Agua Suelo consumida",   "m³"),
    "0_5_12": ("Temp. Impulsión Suelo",  "°C"),
    "0_5_14": ("Temp. Retorno Suelo",    "°C"),
    "0_0_8":  ("Temperatura Exterior",   "°C"),
    "1_0_4":  ("Salón+Cocina Temp Real",       "°C"),
    "1_1_4":  ("Dorm. Principal Temp Real",    "°C"),
    "1_2_4":  ("Dorm. 2 Temp Real",           "°C"),
    "1_3_4":  ("Dorm. 3 Temp Real",           "°C"),
    "1_4_4":  ("Dorm. 4 Temp Real",           "°C"),
    "1_0_3":  ("Salón+Cocina Consigna",        "°C"),
    "1_1_3":  ("Dorm. Principal Consigna",     "°C"),
    "1_2_3":  ("Dorm. 2 Consigna",            "°C"),
    "1_3_3":  ("Dorm. 3 Consigna",            "°C"),
    "1_4_3":  ("Dorm. 4 Consigna",            "°C"),
}

BINARY_SENSOR_ADDRESSES = {
    "0_4_2":  "Alarma Inundación",
    "0_4_3":  "Alarma Incendio",
    "0_0_5":  "EV Suelo Radiante",
    "0_0_7":  "Modo Invierno",
    "0_5_13": "Error Sonda Impulsión",
    "1_0_1":  "Salón+Cocina ON/OFF",
    "1_1_1":  "Dorm. Principal ON/OFF",
    "1_2_1":  "Dorm. 2 ON/OFF",
    "1_3_1":  "Dorm. 3 ON/OFF",
    "1_4_1":  "Dorm. 4 ON/OFF",
}

VALVE_ADDRESSES = {
    "0_0_6": "Válvulas Colector",
}

HOST     = "192.168.10.3"
ONNA_ID  = "ONNA_ID"
PORT     = 4001
LISTEN_S = 8           # seconds to wait after READ_CONFIGURATION

received: dict = {}


async def run():
    import aiohttp

    url = f"ws://{HOST}:{PORT}/socket.io/?EIO=3&transport=websocket&onnaId={ONNA_ID}"
    print(f"Connecting to {url} …\n")

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            # consume EIO open frame
            await asyncio.wait_for(ws.receive(), timeout=5)
            # consume namespace connect (40)
            await asyncio.wait_for(ws.receive(), timeout=5)

            # request full state dump  (SIO ACK frame: "421" + JSON)
            frame = '421["READ_CONFIGURATION"]'
            await ws.send_str(frame)
            print(f"Sent READ_CONFIGURATION — collecting for {LISTEN_S}s …\n")

            async def collect():
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    raw = msg.data
                    if raw == "2":
                        await ws.send_str("3")
                        continue

                    # READ_CONFIGURATION ACK: "431[{...}]"
                    if raw.startswith("431"):
                        try:
                            ack_data = json.loads(raw[3:])
                            # payload is a list; first element is the config dict
                            config = ack_data[0] if isinstance(ack_data, list) else ack_data
                            addresses = config.get("addresses", {})
                            for addr, info in addresses.items():
                                if isinstance(info, dict) and "value" in info:
                                    if addr not in received:
                                        received[addr] = info["value"]
                        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
                            pass
                        continue

                    if not raw.startswith("42"):
                        continue
                    try:
                        data = json.loads(raw[2:])
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if not isinstance(data, list) or len(data) < 2:
                        continue
                    event, payload = data[0], data[1]
                    if event == "SET_ADDRESS_VALUE_FROM_SERVER" and isinstance(payload, dict):
                        addr = payload.get("id")
                        val  = payload.get("value")
                        if addr and addr not in received:
                            received[addr] = val

            try:
                await asyncio.wait_for(collect(), timeout=LISTEN_S)
            except asyncio.TimeoutError:
                pass

    _report()


def _report():
    GREEN  = "\033[32m"
    RED    = "\033[31m"
    YELLOW = "\033[33m"
    RESET  = "\033[0m"

    def row(ok, addr, label, value=""):
        mark  = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        val   = f"  →  {value}" if ok else ""
        print(f"  {mark}  {addr:<10}  {label:<35}{val}")

    print("\n" + "=" * 65)
    print("SENSOR (numeric)")
    print("=" * 65)
    for addr, (name, unit) in SENSOR_ADDRESSES.items():
        label = f"{name} [{unit}]"
        if addr in received:
            row(True, addr, label, received[addr])
        else:
            row(False, addr, label)

    print("\n" + "=" * 65)
    print("BINARY SENSOR")
    print("=" * 65)
    for addr, name in BINARY_SENSOR_ADDRESSES.items():
        if addr in received:
            row(True, addr, name, received[addr])
        else:
            row(False, addr, name)

    print("\n" + "=" * 65)
    print("VALVE")
    print("=" * 65)
    for addr, name in VALVE_ADDRESSES.items():
        if addr in received:
            row(True, addr, name, received[addr])
        else:
            row(False, addr, name)

    unknown = set(received) - set(SENSOR_ADDRESSES) - set(BINARY_SENSOR_ADDRESSES) - set(VALVE_ADDRESSES)
    if unknown:
        print("\n" + "=" * 65)
        print(f"UNKNOWN addresses (received but not mapped)  {YELLOW}↓{RESET}")
        print("=" * 65)
        for addr in sorted(unknown):
            print(f"  {YELLOW}?{RESET}  {addr:<10}  {received[addr]}")

    total   = len(SENSOR_ADDRESSES) + len(BINARY_SENSOR_ADDRESSES) + len(VALVE_ADDRESSES)
    ok      = sum(1 for a in list(SENSOR_ADDRESSES) + list(BINARY_SENSOR_ADDRESSES) + list(VALVE_ADDRESSES) if a in received)
    print(f"\n  {ok}/{total} mapped addresses received data in {LISTEN_S}s\n")


asyncio.run(run())
