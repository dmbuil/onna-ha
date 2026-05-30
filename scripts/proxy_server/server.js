/**
 * Proxy transparente para Onna socket.io v2.
 * - Escucha en puerto 4001 del Mac
 * - Conecta al Pi real (192.168.10.3:4001)
 * - Registra TODOS los eventos en ambas direcciones
 *
 * Úsalo: configura la app del móvil para apuntar a la IP del Mac.
 * Si la app no permite cambiar el servidor, edita /etc/hosts en el router.
 */

const { createServer } = require('http');
const { Server }       = require('socket.io');
const { io: SioClient } = require('socket.io-client');

const REAL_HOST = '192.168.10.3';
const REAL_PORT = 4001;
const LISTEN_PORT = 4001;

const httpServer = createServer();
const serverIo  = new Server(httpServer, {
  cors: { origin: '*' },
  allowEIO3: true,   // Accept EIO v3 clients (socket.io v2)
});

console.log(`[PROXY] Iniciando en puerto ${LISTEN_PORT}`);
console.log(`[PROXY] Upstream: ${REAL_HOST}:${REAL_PORT}\n`);

serverIo.on('connection', (clientSocket) => {
  const onnaId = clientSocket.handshake.query.onnaId || '?';
  const ip     = clientSocket.handshake.address;
  console.log(`[+] Cliente conectado: ${ip}  onnaId=${onnaId}`);

  // Connect upstream
  const upstream = SioClient(`http://${REAL_HOST}:${REAL_PORT}`, {
    query: { onnaId },
    transports: ['websocket'],
    forceNew: true,
  });

  upstream.on('connect', () => {
    console.log(`    [UP] Conectado al Pi`);
  });

  upstream.on('disconnect', (reason) => {
    console.log(`    [UP] Desconectado: ${reason}`);
    clientSocket.disconnect();
  });

  // Relay ALL events from upstream → client
  upstream.onAny((event, ...args) => {
    const t = new Date().toTimeString().slice(0, 8);
    console.log(`  ${t}  Pi→App  [${event}]  ${JSON.stringify(args).slice(0, 120)}`);
    clientSocket.emit(event, ...args);
  });

  // Relay ALL events from client → upstream
  clientSocket.onAny((event, ...args) => {
    const t = new Date().toTimeString().slice(0, 8);
    console.log(`  ${t}  App→Pi  [${event}]  ${JSON.stringify(args).slice(0, 120)}  ← ¡ESCRITURA DEL MÓVIL!`);
    upstream.emit(event, ...args);
  });

  clientSocket.on('disconnect', () => {
    console.log(`[-] Cliente desconectado: ${ip}`);
    upstream.disconnect();
  });
});

httpServer.listen(LISTEN_PORT, '0.0.0.0', () => {
  console.log(`[PROXY] Escuchando en 0.0.0.0:${LISTEN_PORT}\n`);
  console.log('Para capturar el móvil, cambia el servidor en la app a la IP de este Mac.');
});
