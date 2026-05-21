#!/usr/bin/env python3
"""
notion_tool.py — Herramienta CRUD de Notion para el agente Scrum Master.

Uso:
  python3 notion_tool.py leer_ideas
  python3 notion_tool.py leer_epicas
  python3 notion_tool.py crear_tarea    '<json>'
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
def get_title(page, field):
    return "".join(p.get("plain_text","") for p in page.get("properties",{}).get(field,{}).get("title",[])).strip()

def get_rich_text(page, field):
    return "".join(p.get("plain_text","") for p in page.get("properties",{}).get(field,{}).get("rich_text",[])).strip()

def get_select(page, field):
    sel = page.get("properties",{}).get(field,{}).get("select")
    return sel.get("name","") if sel else ""

def get_relation_ids(page, field):
    return [r["id"] for r in page.get("properties",{}).get(field,{}).get("relation",[])]

def prop_title(text):      return {"title":      [{"text": {"content": str(text)}}]}
def prop_rich_text(text):  return {"rich_text":  [{"text": {"content": str(text)[:2000]}}]}
def prop_select(option):   return {"select":     {"name": str(option)}}
def prop_number(n):        return {"number":     int(n)}
def prop_relation(ids):    return {"relation":   [{"id": i} for i in ids]}
def prop_multi_select(opts): return {"multi_select": [{"name": str(o)} for o in opts if o]}

# ── Operaciones ────────────────────────────────────────────────────────────────
def leer_epicas():
    result = http("POST", f"https://api.notion.com/v1/databases/{DB_EPICAS}/query", {
        "filter": {"property": "Estado", "select": {"equals": "Activa"}}
    })
    epicas = [{
        "id":          p["id"],
        "nombre":      get_title(p, "Épica"),
        "descripcion": get_rich_text(p, "Descripción"),
        "objetivo":    get_rich_text(p, "Objetivo"),
    } for p in result.get("results", [])]
    print(json.dumps(epicas, ensure_ascii=False, indent=2))


def leer_ideas():
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
            "proyecto":    get_rich_text(p, "Proyecto"),   # ← ruta relativa
            "epica_ids":   get_relation_ids(p, "Épica"),
        })
    print(json.dumps(ideas, ensure_ascii=False, indent=2))


def crear_tarea(payload: dict):
    """
    Payload:
    {
      "nombre":      "Nombre de la tarea",
      "tipo":        "Backend",
      "orden":       1,
      "estimacion":  "M",
      "descripcion": "...",
      "criterios":   "- criterio 1\n- criterio 2",
      "stack":       ["Node.js", "TypeScript"],
      "idea_id":     "uuid",
      "epica_id":    "uuid"  (opcional)
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
    Payload:
    {
      "id":       "uuid",
      "estado":   "En progreso",  (opcional)
      "epica_id": "uuid"          (opcional)
    }
    """
    props = {}
    if "estado"   in payload: props["Estado"] = prop_select(payload["estado"])
    if "epica_id" in payload: props["Épica"]  = prop_relation([payload["epica_id"]])

    if not props:
        print(json.dumps({"ok": False, "error": "Nada que actualizar"}))
        return

    http("PATCH", f"https://api.notion.com/v1/pages/{payload['id']}", {"properties": props})
    print(json.dumps({"ok": True, "id": payload["id"]}, ensure_ascii=False))


# ── Dispatcher ─────────────────────────────────────────────────────────────────
COMANDOS = {
    "leer_epicas":     lambda _: leer_epicas(),
    "leer_ideas":      lambda _: leer_ideas(),
    "crear_tarea":     lambda a: crear_tarea(json.loads(a)),
    "actualizar_idea": lambda a: actualizar_idea(json.loads(a)),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        print(f"Uso: python3 notion_tool.py <comando> [payload_json]")
        print(f"Comandos: {', '.join(COMANDOS)}")
        sys.exit(1)
    COMANDOS[sys.argv[1]](sys.argv[2] if len(sys.argv) > 2 else "")
