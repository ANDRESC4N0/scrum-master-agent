#!/usr/bin/env python3
"""
notion_tool.py — Herramienta CRUD de Notion para el agente Developer.

Uso:
  python3 notion_tool.py leer_tareas
  python3 notion_tool.py leer_tarea        '<json>'
  python3 notion_tool.py actualizar_tarea  '<json>'
  python3 notion_tool.py comentar_tarea    '<json>'
  python3 notion_tool.py comentar_idea     '<json>'
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

def get_number(page, field):
    return page.get("properties",{}).get(field,{}).get("number")

def get_multi_select(page, field):
    opts = page.get("properties",{}).get(field,{}).get("multi_select",[])
    return [o.get("name","") for o in opts]

def get_relation_ids(page, field):
    return [r["id"] for r in page.get("properties",{}).get(field,{}).get("relation",[])]

def prop_select(option):  return {"select":    {"name": str(option)}}
def prop_rich_text(text): return {"rich_text": [{"text": {"content": str(text)[:2000]}}]}

# ── Operaciones ────────────────────────────────────────────────────────────────
def leer_tareas():
    """
    Lee todas las tareas en estado Backlog ordenadas por Orden ascendente.
    Agrupa por Idea origen para que el agente entienda el contexto completo.
    """
    result = http("POST", f"https://api.notion.com/v1/databases/{DB_TAREAS}/query", {
        "filter": {"property": "Estado", "select": {"equals": "Backlog"}},
        "sorts":  [{"property": "Orden", "direction": "ascending"}]
    })

    tareas = []
    for p in result.get("results", []):
        idea_ids = get_relation_ids(p, "Idea origen")

        # Leer nombre de la idea origen si existe
        idea_titulo = ""
        if idea_ids:
            try:
                idea_page = http("GET", f"https://api.notion.com/v1/pages/{idea_ids[0]}", None)
                idea_titulo = get_title(idea_page, "Idea")
            except:
                idea_titulo = idea_ids[0]

        tareas.append({
            "id":          p["id"],
            "nombre":      get_title(p, "Tarea"),
            "tipo":        get_select(p, "Tipo"),
            "orden":       get_number(p, "Orden"),
            "estimacion":  get_select(p, "Estimación"),
            "estado":      get_select(p, "Estado"),
            "descripcion": get_rich_text(p, "Descripción técnica"),
            "criterios":   get_rich_text(p, "Criterios de aceptación"),
            "stack":       get_multi_select(p, "Stack"),
            "idea_id":     idea_ids[0] if idea_ids else None,
            "idea_titulo": idea_titulo,
            "epica_ids":   get_relation_ids(p, "Épica"),
        })

    print(json.dumps(tareas, ensure_ascii=False, indent=2))


def leer_tarea(payload: dict):
    """
    Lee el detalle completo de una tarea por ID, incluyendo comentarios.
    Payload: { "id": "uuid" }
    """
    page = http("GET", f"https://api.notion.com/v1/pages/{payload['id']}", None)

    # Leer comentarios de la tarea
    comentarios_result = http("GET",
        f"https://api.notion.com/v1/comments?block_id={payload['id']}", None)
    comentarios = []
    for c in comentarios_result.get("results", []):
        texto = "".join(
            rt.get("plain_text", "")
            for rt in c.get("rich_text", [])
        )
        comentarios.append({
            "id":        c["id"],
            "texto":     texto,
            "creado_en": c.get("created_time", ""),
        })

    idea_ids = get_relation_ids(page, "Idea origen")
    tarea = {
        "id":          page["id"],
        "nombre":      get_title(page, "Tarea"),
        "tipo":        get_select(page, "Tipo"),
        "orden":       get_number(page, "Orden"),
        "estimacion":  get_select(page, "Estimación"),
        "estado":      get_select(page, "Estado"),
        "descripcion": get_rich_text(page, "Descripción técnica"),
        "criterios":   get_rich_text(page, "Criterios de aceptación"),
        "stack":       get_multi_select(page, "Stack"),
        "idea_id":     idea_ids[0] if idea_ids else None,
        "comentarios": comentarios,
    }
    print(json.dumps(tarea, ensure_ascii=False, indent=2))


def actualizar_tarea(payload: dict):
    """
    Actualiza el estado de una tarea.
    Payload:
    {
      "id":     "uuid",
      "estado": "En curso" | "QA" | "Hecho"
    }
    """
    props = {}
    if "estado" in payload:
        props["Estado"] = prop_select(payload["estado"])

    if not props:
        print(json.dumps({"ok": False, "error": "Nada que actualizar"}))
        return

    http("PATCH", f"https://api.notion.com/v1/pages/{payload['id']}", {"properties": props})
    print(json.dumps({"ok": True, "id": payload["id"], "estado": payload.get("estado")}))


def comentar_tarea(payload: dict):
    """
    Agrega un comentario a una tarea.
    Payload:
    {
      "id":      "uuid",
      "mensaje": "Texto del comentario"
    }
    """
    http("POST", "https://api.notion.com/v1/comments", {
        "parent":    {"page_id": payload["id"]},
        "rich_text": [{"text": {"content": str(payload["mensaje"])[:2000]}}]
    })
    print(json.dumps({"ok": True, "id": payload["id"]}))


def comentar_idea(payload: dict):
    """
    Agrega un comentario a la idea origen (para comunicación con el Scrum Master).
    Payload:
    {
      "id":      "uuid de la idea",
      "mensaje": "Texto del comentario"
    }
    """
    http("POST", "https://api.notion.com/v1/comments", {
        "parent":    {"page_id": payload["id"]},
        "rich_text": [{"text": {"content": str(payload["mensaje"])[:2000]}}]
    })
    print(json.dumps({"ok": True, "id": payload["id"]}))


# ── Dispatcher ─────────────────────────────────────────────────────────────────
COMANDOS = {
    "leer_tareas":     lambda _: leer_tareas(),
    "leer_tarea":      lambda a: leer_tarea(json.loads(a)),
    "actualizar_tarea": lambda a: actualizar_tarea(json.loads(a)),
    "comentar_tarea":  lambda a: comentar_tarea(json.loads(a)),
    "comentar_idea":   lambda a: comentar_idea(json.loads(a)),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        print(f"Uso: python3 notion_tool.py <comando> [payload_json]")
        print(f"Comandos: {', '.join(COMANDOS)}")
        sys.exit(1)
    COMANDOS[sys.argv[1]](sys.argv[2] if len(sys.argv) > 2 else "")