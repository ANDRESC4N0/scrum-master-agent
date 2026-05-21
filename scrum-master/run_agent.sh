#!/bin/bash
# run_agent.sh — Ejecuta el Scrum Master Agent localmente
# Uso: ./run_agent.sh [max_ideas]

set -e

AGENT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Cargar .env
if [ -f "$AGENT_DIR/.env" ]; then
  export $(grep -v '^#' "$AGENT_DIR/.env" | grep -v '^$' | xargs)
  echo "✅ Variables cargadas desde .env"
fi

# Validar variables requeridas
for var in NOTION_TOKEN NOTION_DB_EPICAS NOTION_DB_IDEAS NOTION_DB_TAREAS BASE_PATH RAMA_BASE; do
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

# Límite de ideas opcional
if [ -n "$1" ]; then
  export MAX_IDEAS_POR_EJECUCION="$1"
fi

echo ""
echo "🤖 Scrum Master Agent"
echo "📁 Base: $BASE_PATH"
echo "🌿 Rama base: $RAMA_BASE"
echo "📐 Estándares: $BASE_PATH/$STANDARDS_DIR"
[ -n "$MAX_IDEAS_POR_EJECUCION" ] && echo "📋 Límite: $MAX_IDEAS_POR_EJECUCION ideas"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ejecutar desde la ruta base para que el agente vea el CLAUDE.md raíz
cd "$BASE_PATH"
claude --dangerously-skip-permissions --print "$(cat "$AGENT_DIR/scrum_master_local.md")"
