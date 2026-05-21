#!/usr/bin/env python3
"""
Scrum Master Agent — Procesa ideas de negocio y genera tareas técnicas en Notion.
Usa la API REST de Notion directamente (sin conector MCP).
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime

# ── Configuración ──────────────────────────────────────────────────────────────
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
if not NOTION_TOKEN:
    raise EnvironmentError("Variable de entorno NOTION_TOKEN no encontrada.")

DB_EPICAS    = "69bcd21f21954247bb36d2250127a78d"
DB_IDEAS     = "d27afba02d344f12a3aa2f9b49aa9796"
DB_TAREAS    = "798794dc634a40bebb5244f8f6e7bc46"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

MAX_IDEAS_POR_EJECUCION = 3

# ── Cliente HTTP mínimo ────────────────────────────────────────────────────────
def notion_request(method: str, path: str, body: dict = None) -> dict:
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = json.loads(e.read())
        raise RuntimeError(f"Notion API {method} {path} → {e.code}: {error_body}")


def query_db(db_id: str, filters: dict = None, sorts: list = None) -> list:
    body = {}
    if filters:
        body["filter"] = filters
    if sorts:
        body["sorts"] = sorts
    result = notion_request("POST", f"/databases/{db_id}/query", body)
    return result.get("results", [])


def create_page(db_id: str, properties: dict, content_blocks: list = None) -> dict:
    body = {
        "parent": {"database_id": db_id},
        "properties": properties,
    }
    if content_blocks:
        body["children"] = content_blocks
    return notion_request("POST", "/pages", body)


def update_page(page_id: str, properties: dict) -> dict:
    return notion_request("PATCH", f"/pages/{page_id}", {"properties": properties})


# ── Helpers de propiedades Notion ──────────────────────────────────────────────
def get_title(page: dict, field: str = "Idea") -> str:
    prop = page.get("properties", {}).get(field, {})
    parts = prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()


def get_select(page: dict, field: str) -> str:
    sel = page.get("properties", {}).get(field, {}).get("select")
    return sel.get("name", "") if sel else ""


def get_relation_ids(page: dict, field: str) -> list:
    rels = page.get("properties", {}).get(field, {}).get("relation", [])
    return [r["id"] for r in rels]


def prop_title(text: str) -> dict:
    return {"title": [{"text": {"content": text}}]}


def prop_rich_text(text: str) -> dict:
    return {"rich_text": [{"text": {"content": text[:2000]}}]}


def prop_select(option: str) -> dict:
    return {"select": {"name": option}}


def prop_multi_select(options: list) -> dict:
    return {"multi_select": [{"name": o} for o in options]}


def prop_number(n: int) -> dict:
    return {"number": n}


def prop_relation(page_ids: list) -> dict:
    return {"relation": [{"id": pid} for pid in page_ids]}


def to_blocks(text: str) -> list:
    """Convierte texto plano a bloques de párrafo para el cuerpo de la página."""
    blocks = []
    for line in text.strip().split("\n"):
        if line.strip():
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line[:2000]}}]
                }
            })
    return blocks[:100]  # Notion max 100 bloques por request


# ── Lógica principal ───────────────────────────────────────────────────────────
def get_epicas_activas() -> list:
    print("📖 Leyendo épicas activas...")
    return query_db(DB_EPICAS, filters={
        "property": "Estado",
        "select": {"equals": "Activa"}
    })


def get_ideas_pendientes() -> list:
    print("📖 Leyendo ideas pendientes...")
    ideas = query_db(
        DB_IDEAS,
        filters={"property": "Estado", "select": {"equals": "Pendiente"}},
        sorts=[{"property": "Prioridad", "direction": "ascending"}]
    )
    # Filtrar bloqueadas por si acaso
    return [i for i in ideas if get_select(i, "Estado") != "Bloqueado"]


def inferir_epica(idea_titulo: str, idea_desc: str, epicas: list) -> str | None:
    """Retorna el page_id de la épica más relevante, o None si no hay match."""
    if not epicas:
        return None
    idea_lower = (idea_titulo + " " + idea_desc).lower()
    for epica in epicas:
        nombre = get_title(epica, "Épica").lower()
        desc   = "".join(
            p.get("plain_text", "")
            for p in epica.get("properties", {}).get("Descripción", {}).get("rich_text", [])
        ).lower()
        palabras = [w for w in (nombre + " " + desc).split() if len(w) > 3]
        if any(p in idea_lower for p in palabras):
            return epica["id"]
    return None


def descomponer_idea(titulo: str, descripcion: str, stack: str) -> list:
    """
    Genera tareas técnicas estructuradas a partir de una idea de negocio.
    Retorna lista de dicts con los campos de cada tarea.
    """
    stack_tags = ["TypeScript", "React", "Node.js", "PostgreSQL"]
    if stack:
        sl = stack.lower()
        if "python"     in sl: stack_tags = ["Python", "PostgreSQL"]
        if "next"       in sl: stack_tags = ["Next.js", "TypeScript", "PostgreSQL"]
        if "mongo"      in sl: stack_tags.append("MongoDB")
        if "docker"     in sl: stack_tags.append("Docker")
        if "graphql"    in sl: stack_tags.append("GraphQL")

    tareas = [
        {
            "nombre": f"[DB] Diseñar esquema de datos para: {titulo}",
            "tipo": "DB",
            "orden": 1,
            "estimacion": "M",
            "descripcion": (
                f"Diseñar y documentar el modelo de datos necesario para '{titulo}'.\n"
                "Incluir: entidades principales, relaciones, índices clave y estrategia de migración.\n"
                "Validar tipos de datos, constraints y normalización antes de implementar."
            ),
            "criterios": (
                "- Diagrama ER o esquema documentado en /docs\n"
                "- Script de migración listo para ejecutar\n"
                "- Revisión de tipos y constraints completada\n"
                "- Aprobado por el equipo antes de pasar al backend"
            ),
            "stack": ["PostgreSQL", "TypeScript"],
        },
        {
            "nombre": f"[Backend] Implementar lógica de negocio y API para: {titulo}",
            "tipo": "Backend",
            "orden": 2,
            "estimacion": "L",
            "descripcion": (
                f"Crear los endpoints REST necesarios para '{titulo}'.\n"
                "Incluir: validación de inputs con zod/joi, autenticación JWT, manejo de errores HTTP estándar, "
                "logging estructurado y documentación OpenAPI básica.\n"
                "Considerar: rate limiting, paginación si aplica, y transacciones de BD."
            ),
            "criterios": (
                "- Endpoints documentados y respondiendo con status codes correctos\n"
                "- Validación de inputs en todas las rutas\n"
                "- Tests unitarios de la lógica de negocio (cobertura > 70%)\n"
                "- Manejo de errores sin exponer stack traces al cliente\n"
                "- Variables de entorno documentadas en .env.example"
            ),
            "stack": [t for t in stack_tags if t in ["Node.js", "Python", "TypeScript", "PostgreSQL", "MongoDB", "REST API", "GraphQL"]],
        },
        {
            "nombre": f"[Frontend] Crear interfaz de usuario para: {titulo}",
            "tipo": "Frontend",
            "orden": 3,
            "estimacion": "L",
            "descripcion": (
                f"Desarrollar los componentes y vistas necesarias para '{titulo}'.\n"
                "Incluir: estado de carga, manejo de errores visible al usuario, formularios con validación "
                "client-side, feedback visual en acciones async, y diseño responsive.\n"
                "Integrar con los endpoints del backend usando fetch/axios con manejo de tokens."
            ),
            "criterios": (
                "- Componentes renderizando correctamente en mobile y desktop\n"
                "- Estados de loading, error y vacío implementados\n"
                "- Formularios con validación y mensajes claros al usuario\n"
                "- Integración con API probada en ambiente de desarrollo\n"
                "- Sin console.errors ni warnings en producción"
            ),
            "stack": [t for t in stack_tags if t in ["React", "Next.js", "TypeScript", "Tailwind"]],
        },
        {
            "nombre": f"[Test] QA y pruebas de integración para: {titulo}",
            "tipo": "Test",
            "orden": 4,
            "estimacion": "M",
            "descripcion": (
                f"Escribir y ejecutar pruebas de integración end-to-end para '{titulo}'.\n"
                "Cubrir: flujo feliz completo, casos edge principales, manejo de errores de red, "
                "y validación de permisos. Usar Playwright o Cypress para E2E si aplica."
            ),
            "criterios": (
                "- Flujo principal cubierto con tests E2E\n"
                "- Al menos 3 casos edge documentados y testeados\n"
                "- Tests corriendo en CI sin flakiness\n"
                "- Reporte de cobertura generado"
            ),
            "stack": ["TypeScript"],
        },
    ]

    # Si el stack tiene Docker/Infra, agregar tarea de deploy
    if any(t in stack_tags for t in ["Docker"]) or "infra" in descripcion.lower() or "deploy" in descripcion.lower():
        tareas.append({
            "nombre": f"[Infra] Configurar deploy para: {titulo}",
            "tipo": "Infra",
            "orden": 5,
            "estimacion": "M",
            "descripcion": (
                f"Configurar pipeline de CI/CD y entorno de deploy para '{titulo}'.\n"
                "Incluir: Dockerfile, variables de entorno en el servidor, health checks y rollback strategy."
            ),
            "criterios": (
                "- Pipeline de CI corriendo en cada PR\n"
                "- Deploy automático a staging en merge a main\n"
                "- Health check endpoint respondiendo\n"
                "- Runbook de deploy documentado"
            ),
            "stack": ["Docker"],
        })

    return tareas


def crear_tareas_en_notion(tareas: list, idea_id: str, epica_id: str | None) -> int:
    creadas = 0
    for t in tareas:
        props = {
            "Tarea":               prop_title(t["nombre"]),
            "Tipo":                prop_select(t["tipo"]),
            "Orden":               prop_number(t["orden"]),
            "Estimación":          prop_select(t["estimacion"]),
            "Estado":              prop_select("Backlog"),
            "Descripción técnica": prop_rich_text(t["descripcion"]),
            "Criterios de aceptación": prop_rich_text(t["criterios"]),
            "Stack":               prop_multi_select(t.get("stack", [])),
            "Idea origen":         prop_relation([idea_id]),
        }
        if epica_id:
            props["Épica"] = prop_relation([epica_id])

        create_page(DB_TAREAS, props)
        creadas += 1
        print(f"  ✅ Tarea creada: {t['nombre']}")

    return creadas


def procesar_ideas():
    print(f"\n🤖 Scrum Master Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    epicas  = get_epicas_activas()
    ideas   = get_ideas_pendientes()

    if not ideas:
        print("✨ No hay ideas pendientes. Nada que procesar.")
        return

    ideas_a_procesar = ideas[:MAX_IDEAS_POR_EJECUCION]
    print(f"📋 Ideas a procesar: {len(ideas_a_procesar)} de {len(ideas)} pendientes\n")

    for idea in ideas_a_procesar:
        idea_id    = idea["id"]
        titulo     = get_title(idea, "Idea")
        prioridad  = get_select(idea, "Prioridad")
        stack      = "".join(
            p.get("plain_text", "")
            for p in idea.get("properties", {}).get("Stack sugerido", {}).get("rich_text", [])
        )
        descripcion = "".join(
            p.get("plain_text", "")
            for p in idea.get("properties", {}).get("Descripción", {}).get("rich_text", [])
        )

        print(f"🔍 Procesando: '{titulo}' [{prioridad}]")

        # Determinar épica
        epica_ids = get_relation_ids(idea, "Épica")
        if epica_ids:
            epica_id = epica_ids[0]
            print(f"  🏔️  Épica ya asignada: {epica_id}")
        else:
            epica_id = inferir_epica(titulo, descripcion, epicas)
            if epica_id:
                print(f"  🏔️  Épica inferida: {epica_id}")
                update_page(idea_id, {"Épica": prop_relation([epica_id])})
            else:
                print("  ⚠️  Sin épica asignada (ninguna hace match)")

        # Descomponer en tareas
        tareas = descomponer_idea(titulo, descripcion, stack)

        # Si la idea es ambigua, solo crear tarea de refinamiento
        if len(descripcion.strip()) < 30:
            print("  ⚠️  Descripción muy corta — creando tarea de refinamiento")
            tareas = [{
                "nombre": f"Refinamiento: {titulo}",
                "tipo": "Test",
                "orden": 1,
                "estimacion": "S",
                "descripcion": (
                    f"La idea '{titulo}' no tiene suficiente contexto para descomponerse en tareas técnicas.\n"
                    "Reunirse con el equipo para definir: alcance, usuarios afectados, criterios de éxito y stack."
                ),
                "criterios": (
                    "- Descripción de la idea actualizada con al menos 3 párrafos de contexto\n"
                    "- Stack tecnológico definido\n"
                    "- Criterios de éxito acordados con el equipo"
                ),
                "stack": [],
            }]

        # Crear tareas en Notion
        n = crear_tareas_en_notion(tareas, idea_id, epica_id)

        # Actualizar estado de la idea
        update_page(idea_id, {"Estado": prop_select("En progreso")})
        print(f"  📝 {n} tareas creadas — idea marcada como 'En progreso'\n")

    print("=" * 60)
    print(f"✅ Ejecución completada. {len(ideas_a_procesar)} idea(s) procesada(s).")


if __name__ == "__main__":
    procesar_ideas()
