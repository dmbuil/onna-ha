# Onna API Reference

> Resultado del recon completo. Protocolo descubierto mediante análisis del instalador Windows y captura de tráfico en vivo.

## Protocolo

**Socket.IO v2** (Engine.IO v3, `EIO=3`) sobre **WebSocket**, con fallback a HTTP long-polling.

- **URL base:** `http://192.168.10.3:4001/`
- **Transport:** WebSocket (preferido) o HTTP polling
- **Autenticación:** query parameter `onnaId=<ID>` en todas las requests

El `onnaId` se obtiene del propio dispositivo (etiqueta física o interfaz local).

---

## Flujo de conexión

```
1. GET /socket.io/?EIO=3&transport=polling&onnaId=<ID>
   → { "sid": "...", "upgrades": ["websocket"], "pingInterval": 10000, "pingTimeout": 5000 }

2. GET /socket.io/?EIO=3&transport=websocket&sid=<SID>&onnaId=<ID>
   (con cabeceras Upgrade: websocket)
   → HTTP 101 Switching Protocols

3. WS send: "2probe"   → WS recv: "3probe"
4. WS send: "5"        (upgrade complete)
5. WS send: "40"       (Socket.IO namespace connect en "/")
   ← WS recv: "40"     (namespace connect ack del servidor)

6. A partir de aquí: eventos bidireccionales (ver secciones siguientes)
```

---

## Keepalive

El servidor envía `"2"` (EIO ping) cada 10 segundos. El cliente debe responder `"3"` (EIO pong) dentro de 5 segundos o la sesión expira.

---

## Eventos recibidos (servidor → cliente)

### `SET_ADDRESS_VALUE_FROM_SERVER`

Emitido cuando cambia el valor de cualquier dirección KNX. Es el evento principal de estado en tiempo real.

```json
{
  "id": "1_0_4",
  "value": 21.5
}
```

- `id`: dirección KNX en formato `mainGroup_interGroup_subGroup` (equivale a `1/0/4` en KNX estándar)
- `value`: valor decodificado según el tipo de dato KNX (`type`) de la dirección

---

## Eventos emitidos (cliente → servidor)

### `READ_CONFIGURATION` *(con acknowledgment)*

Solicita la configuración completa del sistema.

```
WS send: 421["READ_CONFIGURATION"]
WS recv: 431[{ addresses, config, community, alarm, thermostats, ... }]
```

La respuesta contiene 148 direcciones KNX organizadas en grupos.

### `SET_ADDRESS_VALUE` *(inferido, no verificado en modo lectura)*

Probable evento para escribir un valor en una dirección KNX.

```json
{
  "id": "1_0_2",
  "value": 22.0
}
```

> ⚠️ No probado. Basado en la convención de nomenclatura `_FROM_SERVER` vs sin sufijo.

---

## Mapa de direcciones KNX

Organizadas por `mainGroup`. Los tipos son KNX DPT estándar:
- `1.001` → booleano (0/1)
- `5.001` → entero 1 byte sin signo (0–255, escalado a 0–100%)
- `9.001` → float 2 bytes (temperatura, humedad, etc.)
- `3.007` → control relativo 4 bits (dimmer step)
- `14.001` → float 4 bytes (potencia, caudal, etc.)
- `13.001` → entero 4 bytes con signo (energía)

### Controles Generales (grupo 0)

| ID | Nombre | Tipo | Notas |
|----|--------|------|-------|
| 0_0_1 | Termostatos General ON/OFF | 1.001 | Control maestro todos los termostatos |
| 0_0_2 | Consigna General | 9.001 | Setpoint global temperatura |
| 0_0_3 | Modo Invierno/Verano General | 1.001 | 0=verano, 1=invierno |
| 0_0_4 | EV Suelo ON/OFF | 1.001 | Electroválvula suelo radiante |
| 0_0_5 | EV Suelo ON/OFF Estado | 1.001 | Estado lectura EV |
| 0_0_6 | Hay válvulas abiertas en el colector? Estado | 1.001 | |
| 0_0_7 | Modo Invierno/Verano General Estado | 1.001 | Estado lectura modo |
| 0_0_8 | Temperatura Exterior | 9.001 | Sensor exterior |
| 0_1_0 | Luz General ON/OFF | 1.001 | Control maestro iluminación |
| 0_1_1 | Luz General ON/OFF Estado | 1.001 | |
| 0_2_0 | Persianas General Mover | 1.001 | 0=subir, 1=bajar |
| 0_2_1 | Persianas General Parar | 1.001 | |
| 0_2_2 | Persianas General A Posición | 5.001 | 0–100% |
| 0_4_2 | Inundación | 1.001 | Alarma inundación |
| 0_4_3 | Incendio | 1.001 | Alarma incendio |
| 0_5_2 | Tensión (V) | 9.001 | Medida eléctrica |
| 0_5_3 | Potencia (W) | 14.001 | Medida eléctrica en tiempo real |
| 0_5_4 | Intensidad (mA) | 9.001 | |
| 0_5_5 | Energía Consumida (kWh) | 13.001 | Acumulado |
| 0_5_6 | Caudal Agua Fría (L/h) | 9.001 | |
| 0_5_7 | Agua Fría Consumida (m3) | 14.001 | |
| 0_5_8 | Caudal Agua Caliente (L/h) | 9.001 | |
| 0_5_9 | Agua Caliente Consumida (m3) | 14.001 | |
| 0_5_10 | Caudal Agua Suelo (m3/h) | 14.001 | |
| 0_5_11 | Agua Suelo Consumida (m3) | 14.001 | |
| 0_5_12 | Temperatura Impulsión Suelo | 9.001 | Temp. ida suelo radiante |
| 0_5_13 | Error sonda Impulsión Suelo | 1.001 | |
| 0_5_14 | Temperatura Retorno Suelo | 9.001 | Temp. retorno suelo radiante |

### Control Temperatura (grupo 1)

Patrón por zona (`Z` = 0..4 para Salón+Cocina, Dormitorio 1–4):

| ID | Nombre | Tipo |
|----|--------|------|
| 1_Z_0 | [Zona] Termostato ON/OFF | 1.001 |
| 1_Z_1 | [Zona] Termostato ON/OFF Estado | 1.001 |
| 1_Z_2 | [Zona] Temperatura consigna | 9.001 |
| 1_Z_3 | [Zona] Temperatura consigna Estado | 9.001 |
| 1_Z_4 | [Zona] Temperatura real | 9.001 |
| 1_Z_5 | [Zona] Suelo ON/OFF (Cabezal) | 1.001 |
| 1_Z_6 | [Zona] Suelo ON/OFF Estado (Cabezal) | 1.001 |
| 1_Z_7 | [Zona] Demanda Suelo Estado | 1.001 |
| 1_Z_8 | [Zona] Demanda Suelo PI | 5.001 |

Zonas: `0`=Salón+Cocina, `1`=Dormitorio 1 (Ppal), `2`=Dormitorio 2, `3`=Dormitorio 3, `4`=Dormitorio 4

Baños (solo suelo): `1_5_0/1` (Baño 1), `1_6_0/1` (Baño 2)

Fancoil Salón: `1_7_0` (válvula), `1_7_2` (velocidad), `1_7_10` (habilitar)

### Control Iluminación (grupo 2)

| ID | Nombre | Tipo |
|----|--------|------|
| 2_0_0 | Lámpara Salón ON/OFF | 1.001 |
| 2_0_3 | Lámpara Salón Valor | 5.001 |
| 2_0_4 | Lámpara Salón Valor Estado | 5.001 |
| 2_0_5 | Lámpara Comedor ON/OFF | 1.001 |
| 2_0_8 | Lámpara Comedor Valor | 5.001 |
| 2_0_10 | Candileja Salón ON/OFF | 1.001 |
| 2_0_13 | Candileja Salón Valor | 5.001 |
| 2_1_0 | Foco Entrada Dormitorio 1 ON/OFF | 1.001 |
| 2_1_2 | Foco Cama Dormitorio 1 ON/OFF | 1.001 |
| 2_1_4 | Candileja Dormitorio 1 ON/OFF | 1.001 |
| 2_1_7 | Candileja Dormitorio 1 Valor | 5.001 |

### Control Motores / Persianas (grupo 3)

Patrón por zona (`Z` = 0..4):

| ID | Nombre | Tipo |
|----|--------|------|
| 3_Z_0 | Persiana [Z] Mover | 1.001 |
| 3_Z_1 | Persiana [Z] Parar | 1.001 |
| 3_Z_2 | Persiana [Z] A Posición | 5.001 |
| 3_Z_3 | Persiana [Z] Posición Estado | 5.001 |

Zonas: `0`=Persiana 1 Salón, `1`=Persiana 2 Salón, `2`=Dormitorio 1, `3`=Dormitorio 2, `4`=Dormitorio 3... *(ver `04-read-configuration.json` para exactitud)*

### Control Ventilación (grupo 4)

| ID | Nombre | Tipo |
|----|--------|------|
| 4_0_0 | Siber Velocidad Valor | 5.001 |
| 4_0_2 | Siber 1-Habilitar/0-Deshabilitar | 1.001 |
| 4_0_10 | Siber ON/OFF | 1.001 |
| 4_0_11 | Siber ON/OFF Estado | 1.001 |
| 4_1_0 | Medida sensor CO2 | 9.001 |
| 4_1_2 | Medida sensor humedad | 9.001 |

---

## Entidades propuestas para Home Assistant

| HA Entity | Tipo | Direcciones clave |
|-----------|------|-------------------|
| `climate.salon_cocina` | climate | ON/OFF: 1_0_0, setpoint: 1_0_2, temp_actual: 1_0_4 |
| `climate.dormitorio_1` | climate | 1_1_0, 1_1_2, 1_1_4 |
| `climate.dormitorio_2` | climate | 1_2_0, 1_2_2, 1_2_4 |
| `climate.dormitorio_3` | climate | 1_3_0, 1_3_2, 1_3_4 |
| `climate.dormitorio_4` | climate | 1_4_0, 1_4_2, 1_4_4 |
| `light.lampara_salon` | light (dimmable) | ON/OFF: 2_0_0, brightness: 2_0_3 |
| `light.lampara_comedor` | light (dimmable) | 2_0_5, 2_0_8 |
| `cover.persiana_salon_1` | cover | move: 3_0_0, stop: 3_0_1, position: 3_0_2 |
| `sensor.temperatura_exterior` | sensor | 0_0_8 |
| `sensor.potencia_w` | sensor | 0_5_3 |
| `sensor.energia_kwh` | sensor | 0_5_5 |
| `sensor.co2_ppm` | sensor | 4_1_0 |
| `sensor.humedad` | sensor | 4_1_2 |
| `sensor.temp_impulsion_suelo` | sensor | 0_5_12 |
| `fan.ventilacion_siber` | fan | speed: 4_0_0, ON/OFF: 4_0_10 |

---

## Implementación HA — resumen técnico

- **Librería**: `python-socketio[client]` (async) + `aiohttp`
- **Conexión**: WebSocket a `ws://192.168.10.3:4001/socket.io/` con query `{EIO: 3, transport: websocket, onnaId: <ID>}`
- **Estado**: suscribir a `SET_ADDRESS_VALUE_FROM_SERVER` → actualizar entidades HA por `id`
- **Control**: emitir `SET_ADDRESS_VALUE` con `{id, value}` *(pendiente verificar nombre exacto)*
- **Arranque**: emitir `READ_CONFIGURATION` en `on_connect` para cargar estado inicial de todas las direcciones
