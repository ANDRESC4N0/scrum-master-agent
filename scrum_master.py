#!/usr/bin/env python3
"""
Scrum Master Agent — Procesa ideas de negocio y genera tareas técnicas en Notion.
Usa la API REST de Notion + Claude API para análisis inteligente de ideas.
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime

# ── Configuración desde variables de entorno ───────────────────────────────────
def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Variable de entorno requerida no encontrada: {name}")
    return value

NOTION_TOKEN  = require_env("NOTION_TOKEN")
DB_EPICAS     = require_env("NOTION_DB_EPICAS")
DB_IDEAS      = require_env("NOTION_DB_IDEAS")
DB_TAREAS     = require_env("NOTION_DB_TAREAS")
ANTHROPIC_KEY = require_env("ANTHROPIC_API_KEY")

# Opcional: cuántas ideas procesar por ejecución. Sin límite si no se define.
_max_raw  = os.environ.get("MAX_IDEAS_POR_EJECUCION", "").strip()
MAX_IDEAS = int(_max_raw) if _max_raw.isdigit() else None

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

ANTHROPIC_HEADERS = {
    "x-api-key": ANTHROPIC_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

# ── Cliente HTTP ───────────────────────────────────────────────────────────────
def http_post(url: str, headers: dict, body: dict) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            error_body = json.loads(raw)
        except json.JSONDecodeError:
            error_body = raw.decode(errors="replace")
        raise RuntimeError(f"HTTP POST {url} → {e.code}: {error_body}")


def http_patch(url: str, headers: dict, body: dict) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            error_body = json.loads(raw)
        except json.JSONDecodeError:
            error_body = raw.decode(errors="replace")
        raise RuntimeError(f"HTTP PATCH {url} → {e.code}: {error_body}")


# ── Cliente Notion ─────────────────────────────────────────────────────────────
def notion_query(db_id: str, filters: dict = None, sorts: list = None) -> list:
    body = {}
    if filters: body["filter"] = filters
    if sorts:   body["sorts"]  = sorts
    result = http_post(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        NOTION_HEADERS, body
    )
    return result.get("results", [])


def notion_create_page(db_id: str, properties: dict) -> dict:
    return http_post(
        "https://api.notion.com/v1/pages",
        NOTION_HEADERS,
        {"parent": {"database_id": db_id}, "properties": properties}
    )


def notion_update_page(page_id: str, properties: dict) -> dict:
    return http_patch(
        f"https://api.notion.com/v1/pages/{page_id}",
        NOTION_HEADERS,
        {"properties": properties}
    )


# ── Helpers de propiedades Notion ──────────────────────────────────────────────
def get_title(page: dict, field: str) -> str:
    parts = page.get("properties", {}).get(field, {}).get("title", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()

def get_select(page: dict, field: str) -> str:
    sel = page.get("properties", {}).get(field, {}).get("select")
    return sel.get("name", "") if sel else ""

def get_rich_text(page: dict, field: str) -> str:
    parts = page.get("properties", {}).get(field, {}).get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()

def get_relation_ids(page: dict, field: str) -> list:
    return [r["id"] for r in page.get("properties", {}).get(field, {}).get("relation", [])]

def prop_title(text: str) -> dict:
    return {"title": [{"text": {"content": text}}]}

def prop_rich_text(text: str) -> dict:
    return {"rich_text": [{"text": {"content": text[:2000]}}]}

def prop_select(option: str) -> dict:
    return {"select": {"name": option}}

def prop_multi_select(options: list) -> dict:
    return {"multi_select": [{"name": o} for o in options if o]}

def prop_number(n: int) -> dict:
    return {"number": n}

def prop_relation(ids: list) -> dict:
    return {"relation": [{"id": i} for i in ids]}


# ── Claude API ─────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Eres un Scrum Master técnico senior especializado en desarrollo de software fullstack.

Tu trabajo es analizar ideas de negocio y descomponerlas en tareas técnicas precisas, ordenadas y ejecutables por un desarrollador sin necesidad de preguntar nada adicional.

REGLAS CRÍTICAS:
1. Genera SOLO las tareas que realmente necesita la idea. No agregues capas técnicas que no aplican.
   - Una librería/SDK no necesita tareas de Frontend ni de base de datos propia.
   - Un rediseño de UI no necesita tareas de DB ni de Infra.
   - Un pipeline de CI/CD no necesita tareas de Frontend ni de Backend de negocio.
2. La cantidad de tareas depende de la complejidad real de la idea:
   - Simple (1 flujo, sin integraciones): 1-2 tareas
   - Media (varios flujos, alguna integración): 3-4 tareas
   - Compleja (múltiples módulos, integraciones externas, multi-tenant, etc.): 5-8 tareas
3. Las tareas deben estar ordenadas por dependencia lógica (lo que se hace primero va primero).
4. Cada tarea debe ser suficientemente específica para que un desarrollador la ejecute sin preguntar.
5. Las descripciones deben mencionar: qué hacer exactamente, qué patrones/librerías usar, qué casos edge considerar.
6. Los criterios de aceptación deben ser verificables y concretos (mínimo 3 por tarea).

TIPOS DE TAREA DISPONIBLES: DB | Backend | Frontend | Test | Infra
ESTIMACIONES: S (< 2h) | M (2-4h) | L (4-8h) | XL (> 1 día)
STACK DISPONIBLE: React, Next.js, Node.js, Python, PostgreSQL, MongoDB, Docker, TypeScript, Tailwind, REST API, GraphQL

Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin markdown, sin explicaciones.
Formato exacto:
{
  "analisis": "Una línea explicando qué tipo de entregable es esta idea y por qué se eligieron estas capas",
  "tareas": [
    {
      "nombre": "Nombre imperativo claro del tipo [Tipo] Acción: contexto",
      "tipo": "Backend",
      "orden": 1,
      "estimacion": "L",
      "descripcion": "Descripción técnica detallada de qué hacer, cómo y por qué",
      "criterios": "- Criterio verificable 1\\n- Criterio verificable 2\\n- Criterio verificable 3",
      "stack": ["Node.js", "TypeScript"]
    }
  ]
}"""


def analizar_idea_con_claude(titulo: str, descripcion: str, stack: str, epica_nombre: str) -> dict:
    """Llama a Claude para analizar la idea y generar tareas técnicas inteligentes."""

    user_prompt = f"""Analiza esta idea de negocio y genera las tareas técnicas necesarias.

IDEA: {titulo}

DESCRIPCIÓN:
{descripcion}

STACK SUGERIDO: {stack if stack else "No especificado — usa TypeScript/Node.js como base"}

ÉPICA/CONTEXTO DE NEGOCIO: {epica_nombre if epica_nombre else "No asignada"}

Genera las tareas técnicas precisas que un equipo de desarrollo necesita para implementar esta idea."""

    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}]
    }

    response = http_post("https://api.anthropic.com/v1/messages", ANTHROPIC_HEADERS, body)

    raw_text = response["content"][0]["text"].strip()

    # Limpiar posibles backticks de markdown por si acaso
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]

    result = json.loads(raw_text)
    return result


# ── Lógica principal ───────────────────────────────────────────────────────────
def get_epicas_activas() -> list:
    print("📖 Leyendo épicas activas...")
    return notion_query(DB_EPICAS, filters={
        "property": "Estado",
        "select": {"equals": "Activa"}
    })


def get_ideas_pendientes() -> list:
    print("📖 Leyendo ideas pendientes...")
    ideas = notion_query(
        DB_IDEAS,
        filters={"property": "Estado", "select": {"equals": "Pendiente"}},
        sorts=[{"property": "Prioridad", "direction": "ascending"}]
    )
    return [i for i in ideas if get_select(i, "Estado") != "Bloqueado"]


def inferir_epica(titulo: str, descripcion: str, epicas: list) -> tuple[str | None, str]:
    """Retorna (page_id, nombre_epica) de la épica más relevante."""
    if not epicas:
        return None, ""
    texto = (titulo + " " + descripcion).lower()
    for epica in epicas:
        nombre = get_title(epica, "Épica")
        desc   = get_rich_text(epica, "Descripción")
        palabras = [w for w in (nombre + " " + desc).lower().split() if len(w) > 3]
        if any(p in texto for p in palabras):
            return epica["id"], nombre
    return None, ""


def crear_tareas_en_notion(tareas: list, idea_id: str, epica_id: str | None) -> int:
    creadas = 0
    for t in tareas:
        stack_list = t.get("stack", [])
        if isinstance(stack_list, str):
            stack_list = [s.strip() for s in stack_list.split(",")]

        props = {
            "Tarea":                   prop_title(t["nombre"]),
            "Tipo":                    prop_select(t["tipo"]),
            "Orden":                   prop_number(t["orden"]),
            "Estimación":              prop_select(t["estimacion"]),
            "Estado":                  prop_select("Backlog"),
            "Descripción técnica":     prop_rich_text(t.get("descripcion", "")),
            "Criterios de aceptación": prop_rich_text(t.get("criterios", "")),
            "Stack":                   prop_multi_select(stack_list),
            "Idea origen":             prop_relation([idea_id]),
        }
        if epica_id:
            props["Épica"] = prop_relation([epica_id])

        notion_create_page(DB_TAREAS, props)
        creadas += 1
        print(f"  ✅ [{t['tipo']}] {t['nombre']} ({t['estimacion']})")

    return creadas


def procesar_ideas():
    print(f"\n🤖 Scrum Master Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    epicas = get_epicas_activas()
    ideas  = get_ideas_pendientes()

    if not ideas:
        print("✨ No hay ideas pendientes. Nada que procesar.")
        return

    ideas_a_procesar = ideas[:MAX_IDEAS] if MAX_IDEAS else ideas
    limite_txt = f"(límite: {MAX_IDEAS})" if MAX_IDEAS else "(sin límite)"
    print(f"📋 Ideas a procesar: {len(ideas_a_procesar)} de {len(ideas)} pendientes {limite_txt}\n")

    for idea in ideas_a_procesar:
        idea_id     = idea["id"]
        titulo      = get_title(idea, "Idea")
        prioridad   = get_select(idea, "Prioridad")
        stack       = get_rich_text(idea, "Stack sugerido")
        descripcion = get_rich_text(idea, "Descripción")

        print(f"🔍 Procesando: '{titulo}' [{prioridad}]")

        # Determinar épica
        epica_ids = get_relation_ids(idea, "Épica")
        if epica_ids:
            epica_id = epica_ids[0]
            epica_nombre = next(
                (get_title(e, "Épica") for e in epicas if e["id"] == epica_id), ""
            )
            print(f"  🏔️  Épica ya asignada: {epica_nombre}")
        else:
            epica_id, epica_nombre = inferir_epica(titulo, descripcion, epicas)
            if epica_id:
                print(f"  🏔️  Épica inferida: {epica_nombre}")
                notion_update_page(idea_id, {"Épica": prop_relation([epica_id])})
            else:
                print("  ⚠️  Sin épica asignada")

        # Descripción muy corta → refinamiento sin llamar a Claude
        if len(descripcion.strip()) < 30:
            print("  ⚠️  Descripción muy corta — creando tarea de refinamiento")
            tareas = [{
                "nombre": f"Refinamiento: {titulo}",
                "tipo": "Test", "orden": 1, "estimacion": "S",
                "descripcion": (
                    f"La idea '{titulo}' necesita más contexto antes de descomponerse.\n"
                    "Definir: alcance, usuarios objetivo, criterios de éxito y stack tecnológico."
                ),
                "criterios": (
                    "- Descripción actualizada con al menos 3 párrafos de contexto\n"
                    "- Stack tecnológico definido\n"
                    "- Criterios de éxito acordados con el equipo"
                ),
                "stack": [],
            }]
        else:
            # Analizar con Claude
            print("  🧠 Analizando con Claude...")
            resultado = analizar_idea_con_claude(titulo, descripcion, stack, epica_nombre)
            print(f"  📊 Análisis: {resultado.get('analisis', '')}")
            tareas = resultado.get("tareas", [])

        n = crear_tareas_en_notion(tareas, idea_id, epica_id)
        notion_update_page(idea_id, {"Estado": prop_select("En progreso")})
        print(f"  📝 {n} tarea(s) creadas — idea marcada como 'En progreso'\n")

    print("=" * 60)
    print(f"✅ Ejecución completada. {len(ideas_a_procesar)} idea(s) procesada(s).")


if __name__ == "__main__":
    procesar_ideas()
