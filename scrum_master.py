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

# ── Configuración desde variables de entorno ───────────────────────────────────
def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(f"Variable de entorno requerida no encontrada: {name}")
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
        raw = e.read()
        try:
            error_body = json.loads(raw)
        except json.JSONDecodeError:
            error_body = raw.decode(errors="replace")
        raise RuntimeError(f"Notion API {method} {path} → {e.code}: {error_body}")


def query_db(db_id: str, filters: dict = None, sorts: list = None) -> list:
    body = {}
    if filters:
        body["filter"] = filters
    if sorts:
        body["sorts"] = sorts
    result = notion_request("POST", f"/databases/{db_id}/query", body)
    return result.get("results", [])


def create_page(db_id: str, properties: dict) -> dict:
    body = {
        "parent": {"database_id": db_id},
        "properties": properties,
    }
    return notion_request("POST", "/pages", body)


def update_page(page_id: str, properties: dict) -> dict:
    return notion_request("PATCH", f"/pages/{page_id}", {"properties": properties})


# ── Helpers de propiedades Notion ──────────────────────────────────────────────
def get_title(page: dict, field: str) -> str:
    prop = page.get("properties", {}).get(field, {})
    parts = prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()


def get_select(page: dict, field: str) -> str:
    sel = page.get("properties", {}).get(field, {}).get("select")
    return sel.get("name", "") if sel else ""


def get_rich_text(page: dict, field: str) -> str:
    parts = page.get("properties", {}).get(field, {}).get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts).strip()


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
    return [i for i in ideas if get_select(i, "Estado") != "Bloqueado"]


def inferir_epica(titulo: str, descripcion: str, epicas: list) -> str | None:
    if not epicas:
        return None
    idea_lower = (titulo + " " + descripcion).lower()
    for epica in epicas:
        nombre = get_title(epica, "Épica").lower()
        desc   = get_rich_text(epica, "Descripción").lower()
        palabras = [w for w in (nombre + " " + desc).split() if len(w) > 3]
        if any(p in idea_lower for p in palabras):
            return epica["id"]
    return None


def descomponer_idea(titulo: str, descripcion: str, stack: str) -> list:
    stack_tags = ["TypeScript", "React", "Node.js", "PostgreSQL"]
    if stack:
        sl = stack.lower()
        if "python"  in sl: stack_tags = ["Python", "PostgreSQL"]
        if "next"    in sl: stack_tags = ["Next.js", "TypeScript", "PostgreSQL"]
        if "mongo"   in sl: stack_tags.append("MongoDB")
        if "docker"  in sl: stack_tags.append("Docker")
        if "graphql" in sl: stack_tags.append("GraphQL")

    tareas = [
        {
            "nombre": f"[DB] Diseñar esquema de datos para: {titulo}",
            "tipo": "DB", "orden": 1, "estimacion": "M",
            "descripcion": (
                f"Diseñar y documentar el modelo de datos para '{titulo}'.\n\n"
                f"Contexto del dominio: {descripcion[:500]}\n\n"
                "Definir:\n"
                "- Entidades principales y sus atributos con tipos de dato precisos\n"
                "- Relaciones (1:1, 1:N, N:M) y claves foráneas\n"
                "- Índices para las queries más frecuentes del dominio\n"
                "- Estrategia de migración (up/down) sin downtime si es posible\n"
                "- Consideraciones de multi-tenancy, soft-delete o auditoría si aplica"
            ),
            "criterios": (
                f"- Diagrama ER o esquema documentado en /docs para '{titulo}'\n"
                "- Script de migración up/down listo y probado en local\n"
                "- Índices definidos y justificados por las queries esperadas\n"
                "- Revisión de tipos, constraints y normalización completada\n"
                "- Aprobado por el equipo antes de implementar el backend"
            ),
            "stack": ["PostgreSQL", "TypeScript"],
        },
        {
            "nombre": f"[Backend] Implementar API para: {titulo}",
            "tipo": "Backend", "orden": 2, "estimacion": "L",
            "descripcion": (
                f"Crear los endpoints REST necesarios para '{titulo}'.\n\n"
                f"Contexto del dominio: {descripcion[:500]}\n\n"
                "Implementar:\n"
                "- Rutas CRUD con verbos HTTP correctos (GET, POST, PUT/PATCH, DELETE)\n"
                "- Validación de inputs con zod o joi (rechazar payloads inválidos con 400)\n"
                "- Autenticación JWT: verificar token en cada ruta protegida, extraer claims relevantes\n"
                "- Autorización por rol/tenant si aplica al dominio de esta idea\n"
                "- Manejo de errores HTTP estándar (400, 401, 403, 404, 409, 500) sin exponer stack traces\n"
                "- Logging estructurado (JSON) con request_id, user_id, duración y status en cada request\n"
                "- Paginación con cursor o offset en endpoints de listado\n"
                "- Documentación OpenAPI (swagger) de cada endpoint: params, body, responses\n"
                "- Variables de entorno nuevas documentadas en .env.example"
            ),
            "criterios": (
                f"- Todos los endpoints de '{titulo}' responden con status codes correctos\n"
                "- Inputs inválidos retornan 400 con mensaje descriptivo del campo que falla\n"
                "- Requests sin token o con token expirado retornan 401\n"
                "- Tests unitarios de la lógica de negocio con cobertura > 70%\n"
                "- Tests de integración que cubren flujo feliz y al menos 2 casos de error\n"
                "- Ningún stack trace o dato interno expuesto en respuestas de error\n"
                "- Documentación OpenAPI accesible en /api/docs\n"
                "- .env.example actualizado con las nuevas variables"
            ),
            "stack": [t for t in stack_tags if t in ["Node.js", "Python", "TypeScript", "PostgreSQL", "MongoDB", "REST API", "GraphQL"]],
        },
        {
            "nombre": f"[Frontend] Crear interfaz para: {titulo}",
            "tipo": "Frontend", "orden": 3, "estimacion": "L",
            "descripcion": (
                f"Desarrollar componentes y vistas para '{titulo}'.\n\n"
                f"Contexto del dominio: {descripcion[:400]}\n\n"
                "Implementar:\n"
                "- Componentes con estado local (useState/useReducer) y conexión al store global si aplica\n"
                "- Estado de carga (skeleton o spinner), error (mensaje accionable) y vacío (empty state)\n"
                "- Formularios con validación client-side usando react-hook-form + zod\n"
                "- Feedback visual inmediato en acciones async (optimistic update o toast)\n"
                "- Diseño responsive: mobile-first con breakpoints sm/md/lg\n"
                "- Integración con API: fetch/axios con interceptor de token, manejo de 401 y retry"
            ),
            "criterios": (
                f"- Todas las vistas de '{titulo}' renderizan sin errores en mobile y desktop\n"
                "- Estados de loading, error y vacío implementados en cada listado o acción async\n"
                "- Formularios validan en cliente antes de enviar y muestran errores por campo\n"
                "- Token de autenticación se adjunta y renueva correctamente\n"
                "- Sin console.errors ni warnings en build de producción\n"
                "- Revisado en Chrome, Firefox y Safari"
            ),
            "stack": [t for t in stack_tags if t in ["React", "Next.js", "TypeScript", "Tailwind"]],
        },
        {
            "nombre": f"[Test] QA e integración para: {titulo}",
            "tipo": "Test", "orden": 4, "estimacion": "M",
            "descripcion": (
                f"Pruebas de integración y E2E para '{titulo}'.\n\n"
                f"Contexto del dominio: {descripcion[:300]}\n\n"
                "Cubrir:\n"
                "- Flujo feliz completo de extremo a extremo (usuario → UI → API → BD)\n"
                "- Al menos 3 casos edge específicos del dominio (datos límite, permisos, concurrencia)\n"
                "- Manejo de errores de red (timeout, 500, 401)\n"
                "- Validación de permisos: usuario sin rol adecuado no debe acceder\n"
                "- Tests de regresión para bugs conocidos si los hay"
            ),
            "criterios": (
                f"- Flujo principal de '{titulo}' cubierto con test E2E automatizado\n"
                "- Al menos 3 casos edge documentados y testeados\n"
                "- Tests corriendo en CI en cada PR sin flakiness\n"
                "- Reporte de cobertura generado y visible en el PR\n"
                "- Tiempo de ejecución del suite < 5 minutos"
            ),
            "stack": ["TypeScript"],
        },
    ]

    if "docker" in stack.lower() or "infra" in descripcion.lower() or "deploy" in descripcion.lower():
        tareas.append({
            "nombre": f"[Infra] Configurar deploy para: {titulo}",
            "tipo": "Infra", "orden": 5, "estimacion": "M",
            "descripcion": (
                f"Pipeline CI/CD y entorno de deploy para '{titulo}'.\n\n"
                f"Contexto del dominio: {descripcion[:300]}\n\n"
                "Configurar:\n"
                "- Dockerfile multi-stage optimizado (build + runtime mínimo)\n"
                "- Variables de entorno por ambiente (dev/staging/prod) en el servidor\n"
                "- Health check endpoint que valide conexión a BD y dependencias críticas\n"
                "- Estrategia de rollback: deploy anterior disponible en < 2 minutos\n"
                "- Alertas básicas: error rate > 1% o latencia p95 > 2s"
            ),
            "criterios": (
                "- Pipeline CI ejecuta lint + tests + build en cada PR\n"
                "- Deploy automático a staging en merge a main\n"
                "- Health check respondiendo 200 con status de dependencias\n"
                "- Rollback probado y documentado en runbook\n"
                "- Variables de entorno documentadas por ambiente"
            ),
            "stack": ["Docker"],
        })

    return tareas


def crear_tareas_en_notion(tareas: list, idea_id: str, epica_id: str | None) -> int:
    creadas = 0
    for t in tareas:
        props = {
            "Tarea":                   prop_title(t["nombre"]),
            "Tipo":                    prop_select(t["tipo"]),
            "Orden":                   prop_number(t["orden"]),
            "Estimación":              prop_select(t["estimacion"]),
            "Estado":                  prop_select("Backlog"),
            "Descripción técnica":     prop_rich_text(t["descripcion"]),
            "Criterios de aceptación": prop_rich_text(t["criterios"]),
            "Stack":                   prop_multi_select(t.get("stack", [])),
            "Idea origen":             prop_relation([idea_id]),
        }
        if epica_id:
            props["Épica"] = prop_relation([epica_id])

        create_page(DB_TAREAS, props)
        creadas += 1
        print(f"  ✅ {t['nombre']}")

    return creadas


def procesar_ideas():
    print(f"\n🤖 Scrum Master Agent — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    epicas = get_epicas_activas()
    ideas  = get_ideas_pendientes()

    if not ideas:
        print("✨ No hay ideas pendientes. Nada que procesar.")
        return

    ideas_a_procesar = ideas[:MAX_IDEAS_POR_EJECUCION]
    print(f"📋 Ideas a procesar: {len(ideas_a_procesar)} de {len(ideas)} pendientes\n")

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
            print(f"  🏔️  Épica ya asignada")
        else:
            epica_id = inferir_epica(titulo, descripcion, epicas)
            if epica_id:
                print(f"  🏔️  Épica inferida y asignada")
                update_page(idea_id, {"Épica": prop_relation([epica_id])})
            else:
                print("  ⚠️  Sin épica asignada (ninguna hace match)")

        # Descomponer — si descripción muy corta, solo refinamiento
        if len(descripcion.strip()) < 30:
            print("  ⚠️  Descripción muy corta — creando tarea de refinamiento")
            tareas = [{
                "nombre": f"Refinamiento: {titulo}",
                "tipo": "Test", "orden": 1, "estimacion": "S",
                "descripcion": (
                    f"La idea '{titulo}' necesita más contexto antes de descomponerse.\n"
                    "Definir: alcance, usuarios, criterios de éxito y stack tecnológico."
                ),
                "criterios": (
                    "- Descripción actualizada con al menos 3 párrafos\n"
                    "- Stack tecnológico definido\n"
                    "- Criterios de éxito acordados con el equipo"
                ),
                "stack": [],
            }]
        else:
            tareas = descomponer_idea(titulo, descripcion, stack)

        n = crear_tareas_en_notion(tareas, idea_id, epica_id)
        update_page(idea_id, {"Estado": prop_select("En progreso")})
        print(f"  📝 {n} tareas creadas — idea marcada como 'En progreso'\n")

    print("=" * 60)
    print(f"✅ Ejecución completada. {len(ideas_a_procesar)} idea(s) procesada(s).")


if __name__ == "__main__":
    procesar_ideas()
