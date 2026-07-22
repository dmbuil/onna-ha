#!/usr/bin/env bash
#
# deploy_to_ha.sh — Copia el custom component `onna` a un Home Assistant remoto por SSH.
#
# Pensado para HAOS / Supervised con el add-on SSH (config en /config).
# NO reinicia Home Assistant: tras copiar, reinicia tú desde Ajustes → Sistema → Reiniciar
# (o "Restart" en Herramientas para desarrolladores).
#
# Configuración: crea scripts/deploy.env (a partir de scripts/deploy.env.example).
# Ese fichero está gitignoreado para no exponer tu host/IP en el repo.
# También puedes exportar las variables por entorno o pasarlas inline:
#   HA_SSH_HOST=homeassistant.local ./scripts/deploy_to_ha.sh
#
# Uso:
#   ./scripts/deploy_to_ha.sh            # copia real (pide confirmación)
#   ./scripts/deploy_to_ha.sh -n         # dry-run: muestra qué copiaría, sin tocar nada
#   ./scripts/deploy_to_ha.sh -y         # sin confirmación interactiva
#   ./scripts/deploy_to_ha.sh -n -y      # dry-run sin prompt

set -euo pipefail

# ── Colores (solo si la salida es una terminal y NO_COLOR no está definido) ──
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'
  C_CYAN=$'\033[36m'; C_RED=$'\033[31m'
else
  C_RESET=; C_BOLD=; C_DIM=; C_GREEN=; C_YELLOW=; C_BLUE=; C_CYAN=; C_RED=
fi

# ── Localizar la raíz del repo (este script vive en scripts/) ────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Cargar configuración local si existe ─────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/deploy.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

# ── Valores por defecto (sobrescribibles por deploy.env o entorno) ───────────
HA_SSH_HOST="${HA_SSH_HOST:-}"          # obligatorio: IP o hostname del HA
HA_SSH_USER="${HA_SSH_USER:-root}"      # add-on SSH de HAOS: normalmente root
HA_SSH_PORT="${HA_SSH_PORT:-22}"        # 22 por defecto (community add-on suele usar 22222)
HA_CONFIG_DIR="${HA_CONFIG_DIR:-/config}"
HA_SSH_OPTS="${HA_SSH_OPTS:-}"          # opciones extra para ssh (ej. -i ~/.ssh/id_ha)
HA_SUDO="${HA_SUDO:-}"                  # "sudo" si el destino /config es de root (usuario no dueño)

SRC_DIR="$REPO_ROOT/custom_components/onna"
DEST_DIR="$HA_CONFIG_DIR/custom_components/onna"

# ── Parseo de flags ──────────────────────────────────────────────────────────
DRY_RUN=""
ASSUME_YES=""
while getopts ":ny" opt; do
  case "$opt" in
    n) DRY_RUN="--dry-run" ;;
    y) ASSUME_YES="1" ;;
    *) echo "Opción no válida: -$OPTARG" >&2; exit 2 ;;
  esac
done

# ── Validaciones ─────────────────────────────────────────────────────────────
if [[ -z "$HA_SSH_HOST" ]]; then
  echo "${C_RED}✗ Falta HA_SSH_HOST.${C_RESET} Crea scripts/deploy.env (copia deploy.env.example) o expórtalo." >&2
  exit 1
fi
if [[ ! -f "$SRC_DIR/manifest.json" ]]; then
  echo "${C_RED}✗ No encuentro $SRC_DIR/manifest.json${C_RESET} — ¿estructura del repo cambiada?" >&2
  exit 1
fi

SSH_CMD="ssh -p $HA_SSH_PORT $HA_SSH_OPTS"

# ── Resumen ──────────────────────────────────────────────────────────────────
echo "${C_DIM}──────────────────────────────────────────────${C_RESET}"
echo "  ${C_CYAN}Origen ${C_RESET}: $SRC_DIR/"
echo "  ${C_CYAN}Destino${C_RESET}: ${C_BOLD}$HA_SSH_USER@$HA_SSH_HOST${C_RESET}:$DEST_DIR/"
echo "  ${C_CYAN}SSH    ${C_RESET}: puerto $HA_SSH_PORT ${HA_SSH_OPTS:+(opts: $HA_SSH_OPTS)}${HA_SUDO:+ ${C_YELLOW}[sudo]${C_RESET}}"
[[ -n "$DRY_RUN" ]] && echo "  ${C_CYAN}Modo   ${C_RESET}: ${C_YELLOW}DRY-RUN (no se copia nada)${C_RESET}"
echo "${C_DIM}──────────────────────────────────────────────${C_RESET}"

if [[ -z "$DRY_RUN" && -z "$ASSUME_YES" ]]; then
  read -r -p "${C_YELLOW}¿Copiar ahora?${C_RESET} [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || { echo "${C_DIM}Cancelado.${C_RESET}"; exit 0; }
fi

# ── Transferencia por tar-over-ssh ───────────────────────────────────────────
# El add-on SSH de HAOS NO trae rsync (y no es persistente si se instala), pero
# tar sí está siempre disponible (busybox). Enviamos el directorio empaquetado.
TAR_EXCLUDES=(--exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' --exclude='.DS_Store')

if [[ -n "$DRY_RUN" ]]; then
  # Dry-run: listamos lo que se enviaría, sin tocar el HA.
  echo "${C_YELLOW}Ficheros que se enviarían:${C_RESET}"
  tar czf - -C "$SRC_DIR" "${TAR_EXCLUDES[@]}" . | tar tzf - | sed 's/^/  /'
else
  # rm -rf + mkdir emula el --delete de rsync (destino idéntico al origen).
  # $HA_SUDO permite escribir en /config aunque el destino pertenezca a root.
  # Todo en UNA sola conexión SSH → una única petición de contraseña.
  tar czf - -C "$SRC_DIR" "${TAR_EXCLUDES[@]}" . \
    | $SSH_CMD "$HA_SSH_USER@$HA_SSH_HOST" \
        "$HA_SUDO sh -c \"rm -rf '$DEST_DIR' && mkdir -p '$DEST_DIR' && tar xzf - -C '$DEST_DIR'\""
fi

echo ""
if [[ -n "$DRY_RUN" ]]; then
  echo "${C_GREEN}✓ Dry-run completado.${C_RESET} ${C_DIM}Nada se ha modificado.${C_RESET}"
else
  echo "${C_GREEN}${C_BOLD}✓ Componente copiado${C_RESET} a $HA_SSH_HOST:$DEST_DIR"
  echo "  ${C_BLUE}→ Reinicia Home Assistant para cargar los cambios:${C_RESET}"
  echo "    ${C_DIM}Ajustes → Sistema → (⋮) Reiniciar Home Assistant${C_RESET}"
fi
