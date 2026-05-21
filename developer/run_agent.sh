#!/bin/bash
# run_agent.sh — Ejecuta el Developer Agent localmente
# Uso: ./run_agent.sh [max_tareas]

set -e

AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Cargar .env
if [ -f "$AGENT_DIR/.env" ]; then
  export $(grep -v '^#' "$AGENT_DIR/.env" | grep -v '^$' | xargs)
  echo "✅ Variables cargadas desde .env"
fi

# Validar variables requeridas
for var in NOTION_TOKEN NOTION_DB_TAREAS BASE_PATH RAMA_BASE; do
  if [ -z "${!var}" ]; then
    echo "❌ Variable requerida no encontrada: $var"
    exit 1
  fi
done

# Validar que la ruta base existe
if [ ! -d "$BASE_PATH" ]; then
  echo "❌ BASE_PATH no existe: $BASE_PATH"
  exit 1
fi

# Default para STANDARDS_DIR si no está definida
export STANDARDS_DIR="${STANDARDS_DIR:-_standards}"

# Límite de tareas opcional
if [ -n "$1" ]; then
  export MAX_TAREAS_POR_EJECUCION="$1"
fi

echo ""
echo "👨‍💻 Developer Agent"
echo "📁 Base: $BASE_PATH"
echo "🌿 Rama base: $RAMA_BASE"
echo "📐 Estándares: $BASE_PATH/$STANDARDS_DIR"
[ -n "$MAX_TAREAS_POR_EJECUCION" ] && echo "📋 Límite: $MAX_TAREAS_POR_EJECUCION tareas"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$BASE_PATH"
claude --dangerously-skip-permissions --print "$(cat "$AGENT_DIR/developer_local.md")"