#!/usr/bin/env python3
"""
notion_tool.py — Herramienta CRUD de Notion para el agente Scrum Master.
Claude Code la llama con argumentos JSON para leer y escribir en los tableros.

Uso:
  python3 notion_tool.py leer_ideas
  python3 notion_tool.py leer_epicas
  python3 notion_tool.py crear_tarea   '<json>'
  python3 notion_tool.py actualizar_idea '<json>'
"""

import os
import sys
import json
import urllib.request
import urllib.error

# ── Configuración ──────────────────────────────────────────────────────────────
def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Variable requerida no encontrada: {name}")
    return value

NOTION_TOKEN = require_env("NOTION_TOKEN")
DB_EPICAS    = require_env("NOTION_DB_EPICAS")
DB_IDEAS     = require_env("NOTION_DB_IDEAS")
DB_TAREAS    = require_env("NOTION_DB_TAREAS")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ── HTTP ───────────────────────────────────────────────────────────────────────
def http(method: str, url: str, body: dict = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:    error_body = json.loads(raw)
        except: error_body = raw.decode(errors="replace")
        raise RuntimeError(f"{method} {url} → {e.code}: {error_body}")

# ── Helpers ────────────────────────────────────────────────────────────────────
def get_title(page: dict, field: str) -> str:
    parts = page.get("properties", {}).get(field, {}).get("title", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()

def get_rich_text(page: dict, field: str) -> str:
    parts = page.get("properties", {}).get(field, {}).get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()

def get_select(page: dict, field: str) -> str:
    sel = page.get("properties", {}).get(field, {}).get("select")
    return sel.get("name", "") if sel else ""

def get_relation_ids(page: dict, field: str) -> list:
    return [r["id"] for r in page.get("properties", {}).get(field, {}).get("relation", [])]

def prop_title(text: str) -> dict:
    return {"title": [{"text": {"content": str(text)}}]}

def prop_rich_text(text: str) -> dict:
    return {"rich_text": [{"text": {"content": str(text)[:2000]}}]}

def prop_select(option: str) -> dict:
    return {"select": {"name": str(option)}}

def prop_multi_select(options: list) -> dict:
    return {"multi_select": [{"name": str(o)} for o in options if o]}

def prop_number(n) -> dict:
    return {"number": int(n)}

def prop_relation(ids: list) -> dict:
    return {"relation": [{"id": i} for i in ids]}

# ── Operaciones ────────────────────────────────────────────────────────────────
def leer_epicas():
    """Lee todas las épicas activas."""
    result = http("POST", f"https://api.notion.com/v1/databases/{DB_EPICAS}/query", {
        "filter": {"property": "Estado", "select": {"equals": "Activa"}}
    })
    epicas = []
    for p in result.get("results", []):
        epicas.append({
            "id":          p["id"],
            "nombre":      get_title(p, "Épica"),
            "descripcion": get_rich_text(p, "Descripción"),
            "objetivo":    get_rich_text(p, "Objetivo"),
            "estado":      get_select(p, "Estado"),
        })
    print(json.dumps(epicas, ensure_ascii=False, indent=2))


def leer_ideas():
    """Lee todas las ideas con estado Pendiente, ordenadas por prioridad."""
    result = http("POST", f"https://api.notion.com/v1/databases/{DB_IDEAS}/query", {
        "filter": {"property": "Estado", "select": {"equals": "Pendiente"}},
        "sorts":  [{"property": "Prioridad", "direction": "ascending"}]
    })
    ideas = []
    for p in result.get("results", []):
        if get_select(p, "Estado") == "Bloqueado":
            continue
        ideas.append({
            "id":          p["id"],
            "titulo":      get_title(p, "Idea"),
            "descripcion": get_rich_text(p, "Descripción"),
            "prioridad":   get_select(p, "Prioridad"),
            "stack":       get_rich_text(p, "Stack sugerido"),
            "epica_ids":   get_relation_ids(p, "Épica"),
        })
    print(json.dumps(ideas, ensure_ascii=False, indent=2))


def crear_tarea(payload: dict):
    """
    Crea una tarea técnica en Notion.
    Payload esperado:
    {
      "nombre":      "Nombre de la tarea",
      "tipo":        "Backend",           -- DB | Backend | Frontend | Test | Infra
      "orden":       1,
      "estimacion":  "M",                 -- S | M | L | XL
      "descripcion": "Descripción técnica detallada",
      "criterios":   "- Criterio 1\n- Criterio 2",
      "stack":       ["Node.js", "TypeScript"],
      "idea_id":     "page-uuid-de-la-idea",
      "epica_id":    "page-uuid-de-la-epica"   -- opcional
    }
    """
    props = {
        "Tarea":                   prop_title(payload["nombre"]),
        "Tipo":                    prop_select(payload["tipo"]),
        "Orden":                   prop_number(payload["orden"]),
        "Estimación":              prop_select(payload["estimacion"]),
        "Estado":                  prop_select("Backlog"),
        "Descripción técnica":     prop_rich_text(payload.get("descripcion", "")),
        "Criterios de aceptación": prop_rich_text(payload.get("criterios", "")),
        "Stack":                   prop_multi_select(payload.get("stack", [])),
        "Idea origen":             prop_relation([payload["idea_id"]]),
    }
    if payload.get("epica_id"):
        props["Épica"] = prop_relation([payload["epica_id"]])

    result = http("POST", "https://api.notion.com/v1/pages", {
        "parent": {"database_id": DB_TAREAS},
        "properties": props
    })
    print(json.dumps({"ok": True, "id": result["id"], "tarea": payload["nombre"]}, ensure_ascii=False))


def actualizar_idea(payload: dict):
    """
    Actualiza propiedades de una idea.
    Payload esperado:
    {
      "id":       "page-uuid-de-la-idea",
      "estado":   "En progreso",   -- opcional
      "epica_id": "uuid"           -- opcional
    }
    """
    props = {}
    if "estado" in payload:
        props["Estado"] = prop_select(payload["estado"])
    if "epica_id" in payload:
        props["Épica"] = prop_relation([payload["epica_id"]])

    if not props:
        print(json.dumps({"ok": False, "error": "Nada que actualizar"}))
        return

    http("PATCH", f"https://api.notion.com/v1/pages/{payload['id']}", {"properties": props})
    print(json.dumps({"ok": True, "id": payload["id"]}, ensure_ascii=False))


# ── Dispatcher ─────────────────────────────────────────────────────────────────
COMANDOS = {
    "leer_epicas":    lambda _: leer_epicas(),
    "leer_ideas":     lambda _: leer_ideas(),
    "crear_tarea":    lambda arg: crear_tarea(json.loads(arg)),
    "actualizar_idea": lambda arg: actualizar_idea(json.loads(arg)),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        print(f"Uso: python3 notion_tool.py <comando> [payload_json]")
        print(f"Comandos: {', '.join(COMANDOS)}")
        sys.exit(1)

    comando = sys.argv[1]
    argumento = sys.argv[2] if len(sys.argv) > 2 else ""
    COMANDOS[comando](argumento)
