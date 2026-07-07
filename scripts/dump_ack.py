"""
Cross-reference our entity addresses against the READ_CONFIGURATION ACK.
Shows: present/missing, readOnInit, persistent, and KNX type for each address.
"""
import asyncio, json, aiohttp

HOST    = "192.168.10.3"
ONNA_ID = "ONNA_ID"
PORT    = 4001

OUR_ADDRESSES = {
    # sensors
    "0_5_3": "Potencia [W]",
    "0_5_2": "Tensión [V]",
    "0_5_4": "Intensidad [mA]",
    "0_5_5": "Energía consumida [kWh]",
    "0_5_6": "Caudal Agua Fría [L/h]",
    "0_5_7": "Agua Fría consumida [m³]",
    "0_5_8": "Caudal Agua Caliente [L/h]",
    "0_5_9": "Agua Caliente consumida [m³]",
    "0_5_10": "Caudal Agua Suelo [m³/h]",
    "0_5_11": "Agua Suelo consumida [m³]",
    "0_5_12": "Temp. Impulsión Suelo [°C]",
    "0_5_14": "Temp. Retorno Suelo [°C]",
    "0_0_8":  "Temperatura Exterior [°C]",
    "1_0_4": "Salón+Cocina Temp Real [°C]",
    "1_1_4": "Dorm. Principal Temp Real [°C]",
    "1_2_4": "Dorm. 2 Temp Real [°C]",
    "1_3_4": "Dorm. 3 Temp Real [°C]",
    "1_4_4": "Dorm. 4 Temp Real [°C]",
    "1_0_3": "Salón+Cocina Consigna [°C]",
    "1_1_3": "Dorm. Principal Consigna [°C]",
    "1_2_3": "Dorm. 2 Consigna [°C]",
    "1_3_3": "Dorm. 3 Consigna [°C]",
    "1_4_3": "Dorm. 4 Consigna [°C]",
    # binary sensors
    "0_4_2": "Alarma Inundación",
    "0_4_3": "Alarma Incendio",
    "0_0_5": "EV Suelo Radiante",
    "0_0_7": "Modo Invierno",
    "0_5_13": "Error Sonda Impulsión",
    "1_0_1": "Salón+Cocina ON/OFF",
    "1_1_1": "Dorm. Principal ON/OFF",
    "1_2_1": "Dorm. 2 ON/OFF",
    "1_3_1": "Dorm. 3 ON/OFF",
    "1_4_1": "Dorm. 4 ON/OFF",
    # valve
    "0_0_6": "Válvulas Colector",
}

async def run():
    url = f"ws://{HOST}:{PORT}/socket.io/?EIO=3&transport=websocket&onnaId={ONNA_ID}"
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            await asyncio.wait_for(ws.receive(), timeout=5)
            await asyncio.wait_for(ws.receive(), timeout=5)
            await ws.send_str('421["READ_CONFIGURATION"]')

            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                raw = msg.data
                if raw == "2":
                    await ws.send_str("3")
                    continue
                if not raw.startswith("431"):
                    continue

                data = json.loads(raw[3:])
                config    = data[0] if isinstance(data, list) else data
                addresses = config.get("addresses", {})

                G  = "\033[32m"
                R  = "\033[31m"
                Y  = "\033[33m"
                RS = "\033[0m"

                print(f"\n{'='*75}")
                print(f"{'ADDR':<10} {'PRESENT':<9} {'readOnInit':<12} {'persistent':<11} {'type':<10} NAME")
                print(f"{'='*75}")

                for addr, label in OUR_ADDRESSES.items():
                    if addr in addresses:
                        info = addresses[addr]
                        roi  = info.get("readOnInit", False)
                        pers = info.get("persistent", False)
                        typ  = info.get("type", "?")
                        name = info.get("name", "")
                        roi_s  = f"{G}yes{RS}" if roi  else f"{R}no {RS}"
                        pers_s = f"{G}yes{RS}" if pers else "no "
                        print(f"{addr:<10} {G}✓{RS}        {roi_s:<20} {pers_s:<11} {typ:<10} {name}")
                    else:
                        print(f"{addr:<10} {R}✗ MISSING{RS}")

                print(f"\nTotal addresses in device config: {len(addresses)}")
                break

asyncio.run(run())
