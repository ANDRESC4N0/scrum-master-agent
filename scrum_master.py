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

NOTION_TOKEN     = require_env("NOTION_TOKEN")
DB_EPICAS        = require_env("NOTION_DB_EPICAS")
DB_IDEAS         = require_env("NOTION_DB_IDEAS")
DB_TAREAS        = require_env("NOTION_DB_TAREAS")

# Opcional: cuántas ideas procesar por ejecución. Sin límite si no se define.
_max_raw         = os.environ.get("MAX_IDEAS_POR_EJECUCION", "").strip()
MAX_IDEAS        = int(_max_raw) if _max_raw.isdigit() else None

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


def detectar_capas(titulo: str, descripcion: str, stack: str) -> dict:
    """
    Analiza el título, descripción y stack de la idea para determinar
    qué capas técnicas son realmente necesarias.
    Retorna un dict de booleanos: {db, backend, frontend, test, infra}
    """
    texto = (titulo + " " + descripcion + " " + stack).lower()

    # Señales de que NO hay capa de datos nueva
    sin_db = any(w in texto for w in [
        "ui ", "interfaz", "diseño", "dashboard", "componente", "vista", "pantalla",
        "rediseñ", "estilos", "css", "layout", "animacion", "refactor", "pipeline",
        "ci/cd", "lint", "script", "automatiz", "notificacion email", "webhook outbound",
    ])
    # Señales explícitas de que SÍ hay BD
    con_db = any(w in texto for w in [
        "tabla", "esquema", "modelo", "entidad", "relacion", "migración", "migracion",
        "base de datos", "bd ", " db ", "postgresql", "mongodb", "mysql", "sqlite",
        "almacen", "persist", "registro", "históric", "histori", "audit", "log ",
        "store", "repositorio de datos",
    ])
    necesita_db = con_db or (not sin_db and any(w in texto for w in [
        "crud", "guardar", "crear", "editar", "eliminar", "listar", "buscar",
        "api", "endpoint", "servicio", "backend",
    ]))

    # Señales de Frontend
    necesita_fe = any(w in texto for w in [
        "ui", "interfaz", "pantalla", "vista", "dashboard", "componente", "formulario",
        "página", "pagina", "portal", "web", "app", "frontend", "fe ", "usuario ve",
        "diseño", "layout", "rediseñ", "flujo de usuario", "ux", "onboarding",
    ])

    # Señales de Backend / API
    necesita_be = any(w in texto for w in [
        "api", "endpoint", "servicio", "backend", "rest", "graphql", "webhook",
        "autenticacion", "autenticación", "autorización", "autorizacion", "jwt",
        "lógica de negocio", "logica", "procesamiento", "integración", "integracion",
        "notificacion", "notificación", "email", "cron", "job", "queue", "worker",
        "audit", "log ", "crud", "importar", "exportar", "reporte",
    ])
    # Si hay DB o FE probablemente también hay BE
    if necesita_db or necesita_fe:
        necesita_be = True

    # Señales de Infra
    necesita_infra = any(w in texto for w in [
        "deploy", "despliegue", "docker", "ci/cd", "pipeline", "kubernetes", "k8s",
        "servidor", "cloud", "aws", "gcp", "azure", "infra", "ambiente", "entorno",
        "staging", "produccion", "producción", "monitoreo", "alerta", "escalab",
        "contenedor", "helm", "terraform",
    ])

    # Test siempre aplica si hay al menos una capa de código
    necesita_test = necesita_db or necesita_be or necesita_fe or necesita_infra

    return {
        "db":       necesita_db,
        "backend":  necesita_be,
        "frontend": necesita_fe,
        "test":     necesita_test,
        "infra":    necesita_infra,
    }


def detectar_complejidad(titulo: str, descripcion: str) -> str:
    """
    Estima la complejidad de la idea basándose en señales del texto.
    Retorna: 'simple' | 'media' | 'compleja'

    - simple:  1 flujo claro, sin integraciones externas, sin roles complejos
    - media:   varios flujos, alguna integración o lógica de permisos
    - compleja: múltiples módulos, integraciones externas, multi-tenant, alta carga, etc.
    """
    texto = (titulo + " " + descripcion).lower()
    palabras = texto.split()

    # Señales de alta complejidad
    señales_alta = [
        "multitenant", "multi-tenant", "multitenancy", "multi tenancy",
        "microservicio", "microservice", "event sourcing", "cqrs",
        "integración con", "integracion con", "third party", "terceros",
        "concurrencia", "alta disponibilidad", "escalab", "sharding",
        "múltiples módulos", "multiples modulos", "varios servicios",
        "machine learning", "ia ", " ml ", "modelo de ia",
        "tiempo real", "real time", "websocket", "streaming",
        "migración de datos", "migracion de datos", "etl",
        "compliance", "gdpr", "hipaa", "sox", "auditoria completa",
        "sistema de pagos", "pasarela de pago", "facturación",
        "roles y permisos", "rbac", "abac",
    ]

    # Señales de complejidad media
    señales_media = [
        "notificacion", "notificación", "email", "webhook",
        "reporte", "exportar", "importar", "csv", "excel",
        "autenticacion", "autenticación", "login", "registro",
        "búsqueda", "busqueda", "filtros", "paginación",
        "dashboard", "métricas", "estadísticas",
        "integración", "integracion", "api externa",
        "caché", "cache", "cola", "queue", "job",
        "varios", "multiple", "diferentes", "distintos",
    ]

    score_alta  = sum(1 for s in señales_alta  if s in texto)
    score_media = sum(1 for s in señales_media if s in texto)
    longitud    = len(palabras)

    if score_alta >= 2 or (score_alta >= 1 and longitud > 80):
        return "compleja"
    if score_alta == 1 or score_media >= 3 or longitud > 60:
        return "media"
    return "simple"


def descomponer_idea(titulo: str, descripcion: str, stack: str) -> list:
    stack_tags = ["TypeScript", "React", "Node.js", "PostgreSQL"]
    if stack:
        sl = stack.lower()
        if "python"  in sl: stack_tags = ["Python", "PostgreSQL"]
        if "next"    in sl: stack_tags = ["Next.js", "TypeScript", "PostgreSQL"]
        if "mongo"   in sl: stack_tags.append("MongoDB")
        if "docker"  in sl: stack_tags.append("Docker")
        if "graphql" in sl: stack_tags.append("GraphQL")

    capas       = detectar_capas(titulo, descripcion, stack)
    complejidad = detectar_complejidad(titulo, descripcion)
    print(f"  🔎 Capas: { {k for k, v in capas.items() if v} } | Complejidad: {complejidad}")

    tareas = []
    orden  = 1

    # ── DB ─────────────────────────────────────────────────────────────────────
    if capas["db"]:
        if complejidad == "compleja":
            # Separar diseño de implementación/migración
            tareas.append({
                "nombre": f"[DB] Diseñar esquema de datos para: {titulo}",
                "tipo": "DB", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Diseñar y documentar el modelo de datos para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:400]}\n\n"
                    "- Entidades, atributos y tipos de dato precisos\n"
                    "- Relaciones (1:1, 1:N, N:M) y claves foráneas\n"
                    "- Consideraciones de multi-tenancy, soft-delete o auditoría\n"
                    "- Revisión con el equipo antes de implementar"
                ),
                "criterios": (
                    "- Diagrama ER documentado en /docs\n"
                    "- Aprobado por el equipo antes de escribir migraciones"
                ),
                "stack": ["PostgreSQL", "TypeScript"],
            })
            orden += 1
            tareas.append({
                "nombre": f"[DB] Implementar migraciones e índices para: {titulo}",
                "tipo": "DB", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Escribir y validar las migraciones para el esquema aprobado de '{titulo}'.\n\n"
                    "- Scripts up/down sin downtime si es posible\n"
                    "- Índices justificados por las queries más frecuentes\n"
                    "- Datos de seed para desarrollo y staging"
                ),
                "criterios": (
                    "- Migraciones ejecutan sin error en local y staging\n"
                    "- Rollback probado\n"
                    "- Índices creados y verificados con EXPLAIN"
                ),
                "stack": ["PostgreSQL", "TypeScript"],
            })
            orden += 1
        else:
            # Simple o media: una sola tarea de DB
            tareas.append({
                "nombre": f"[DB] Diseñar e implementar esquema para: {titulo}",
                "tipo": "DB", "orden": orden, "estimacion": "S" if complejidad == "simple" else "M",
                "descripcion": (
                    f"Diseñar y aplicar el modelo de datos para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:400]}\n\n"
                    "- Entidades, relaciones e índices necesarios\n"
                    "- Script de migración up/down\n"
                    "- Consideraciones de normalización y constraints"
                ),
                "criterios": (
                    "- Esquema documentado en /docs\n"
                    "- Migración ejecuta sin error en local\n"
                    "- Revisión de tipos y constraints completada"
                ),
                "stack": ["PostgreSQL", "TypeScript"],
            })
            orden += 1

    # ── BACKEND ────────────────────────────────────────────────────────────────
    if capas["backend"]:
        if complejidad == "compleja":
            # Separar lógica de negocio de la capa de API
            tareas.append({
                "nombre": f"[Backend] Implementar lógica de negocio para: {titulo}",
                "tipo": "Backend", "orden": orden, "estimacion": "L",
                "descripcion": (
                    f"Implementar los casos de uso y servicios internos de '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:400]}\n\n"
                    "- Servicios/use-cases desacoplados del transporte HTTP\n"
                    "- Validación de reglas de negocio (no solo de inputs)\n"
                    "- Manejo de transacciones y rollback\n"
                    "- Logging estructurado con contexto de tenant/usuario\n"
                    "- Tests unitarios de cada caso de uso"
                ),
                "criterios": (
                    "- Cada caso de uso tiene tests unitarios con cobertura > 80%\n"
                    "- Lógica sin dependencia directa de HTTP o BD (inversión de dependencias)\n"
                    "- Errores de negocio tipados y diferenciados de errores técnicos"
                ),
                "stack": [t for t in stack_tags if t in ["Node.js", "Python", "TypeScript", "PostgreSQL", "MongoDB"]],
            })
            orden += 1
            tareas.append({
                "nombre": f"[Backend] Implementar API y controladores para: {titulo}",
                "tipo": "Backend", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Exponer los servicios de '{titulo}' via HTTP.\n\n"
                    "- Rutas con verbos HTTP correctos\n"
                    "- Validación de inputs con zod/joi (400 en payload inválido)\n"
                    "- Autenticación JWT y autorización por rol/tenant\n"
                    "- Manejo de errores HTTP sin exponer stack traces\n"
                    "- Documentación OpenAPI de cada endpoint"
                ),
                "criterios": (
                    "- Endpoints responden con status codes correctos\n"
                    "- Tests de integración cubren flujo feliz y casos de error\n"
                    "- OpenAPI accesible en /api/docs\n"
                    "- .env.example actualizado"
                ),
                "stack": [t for t in stack_tags if t in ["Node.js", "Python", "TypeScript", "REST API", "GraphQL"]],
            })
            orden += 1
        else:
            tareas.append({
                "nombre": f"[Backend] Implementar lógica y API para: {titulo}",
                "tipo": "Backend", "orden": orden, "estimacion": "S" if complejidad == "simple" else "L",
                "descripcion": (
                    f"Crear lógica de negocio y endpoints para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:400]}\n\n"
                    "- Rutas con verbos HTTP correctos\n"
                    "- Validación de inputs, autenticación JWT\n"
                    "- Manejo de errores sin exponer stack traces\n"
                    "- Logging estructurado y documentación OpenAPI"
                ),
                "criterios": (
                    "- Endpoints responden con status codes correctos\n"
                    "- Tests unitarios con cobertura > 70%\n"
                    "- OpenAPI accesible en /api/docs\n"
                    "- .env.example actualizado"
                ),
                "stack": [t for t in stack_tags if t in ["Node.js", "Python", "TypeScript", "PostgreSQL", "MongoDB", "REST API", "GraphQL"]],
            })
            orden += 1

    # ── FRONTEND ───────────────────────────────────────────────────────────────
    if capas["frontend"]:
        if complejidad == "compleja":
            tareas.append({
                "nombre": f"[Frontend] Implementar componentes base para: {titulo}",
                "tipo": "Frontend", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Crear los componentes reutilizables necesarios para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:300]}\n\n"
                    "- Componentes atómicos y moleculares (sin lógica de negocio)\n"
                    "- Estados: loading (skeleton), error, vacío\n"
                    "- Diseño responsive mobile-first\n"
                    "- Storybook o documentación visual si aplica"
                ),
                "criterios": (
                    "- Componentes renderizan sin errores en mobile y desktop\n"
                    "- Estados de loading, error y vacío implementados\n"
                    "- Sin console.errors en build de producción"
                ),
                "stack": [t for t in stack_tags if t in ["React", "Next.js", "TypeScript", "Tailwind"]],
            })
            orden += 1
            tareas.append({
                "nombre": f"[Frontend] Integrar flujos y lógica de negocio para: {titulo}",
                "tipo": "Frontend", "orden": orden, "estimacion": "L",
                "descripcion": (
                    f"Conectar los componentes de '{titulo}' con la API y el estado global.\n\n"
                    "- Integración con API: fetch/axios con interceptor de token y manejo de 401\n"
                    "- Formularios con react-hook-form + zod\n"
                    "- Feedback en acciones async (toast, optimistic update)\n"
                    "- Manejo de sesión y redirecciones de autenticación"
                ),
                "criterios": (
                    "- Flujos completos funcionando end-to-end en desarrollo\n"
                    "- Formularios validan antes de enviar y muestran errores por campo\n"
                    "- Revisado en Chrome, Firefox y Safari"
                ),
                "stack": [t for t in stack_tags if t in ["React", "Next.js", "TypeScript", "Tailwind"]],
            })
            orden += 1
        else:
            tareas.append({
                "nombre": f"[Frontend] Crear interfaz para: {titulo}",
                "tipo": "Frontend", "orden": orden, "estimacion": "S" if complejidad == "simple" else "L",
                "descripcion": (
                    f"Desarrollar componentes y vistas para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:400]}\n\n"
                    "- Estados de carga, error y vacío\n"
                    "- Formularios con validación client-side\n"
                    "- Diseño responsive mobile-first\n"
                    "- Integración con API con manejo de token"
                ),
                "criterios": (
                    "- Vistas funcionando en mobile y desktop\n"
                    "- Formularios validan antes de enviar\n"
                    "- Sin console.errors en producción"
                ),
                "stack": [t for t in stack_tags if t in ["React", "Next.js", "TypeScript", "Tailwind"]],
            })
            orden += 1

    # ── TEST ───────────────────────────────────────────────────────────────────
    if capas["test"]:
        if complejidad == "compleja":
            tareas.append({
                "nombre": f"[Test] Tests unitarios y de integración para: {titulo}",
                "tipo": "Test", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Tests de lógica interna para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:300]}\n\n"
                    "- Tests unitarios de servicios y casos de uso\n"
                    "- Tests de integración API ↔ BD\n"
                    "- Casos edge del dominio: datos límite, permisos, concurrencia"
                ),
                "criterios": (
                    "- Cobertura > 70% en lógica de negocio\n"
                    "- Al menos 3 casos edge testeados\n"
                    "- Tests en CI sin flakiness"
                ),
                "stack": ["TypeScript"],
            })
            orden += 1
            tareas.append({
                "nombre": f"[Test] Tests E2E para: {titulo}",
                "tipo": "Test", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Tests end-to-end del flujo completo de '{titulo}'.\n\n"
                    "- Flujo feliz completo (usuario → UI → API → BD)\n"
                    "- Validación de permisos y roles\n"
                    "- Manejo de errores de red (timeout, 500, 401)\n"
                    "- Tests de regresión para bugs conocidos"
                ),
                "criterios": (
                    "- Flujo principal cubierto con test E2E automatizado\n"
                    "- Tests en CI en cada PR\n"
                    "- Tiempo de ejecución < 5 minutos"
                ),
                "stack": ["TypeScript"],
            })
            orden += 1
        else:
            tareas.append({
                "nombre": f"[Test] QA para: {titulo}",
                "tipo": "Test", "orden": orden, "estimacion": "S" if complejidad == "simple" else "M",
                "descripcion": (
                    f"Pruebas para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:300]}\n\n"
                    "- Flujo feliz de las capas implementadas\n"
                    "- Al menos 2 casos edge del dominio\n"
                    "- Validación de permisos si aplica"
                ),
                "criterios": (
                    "- Flujo principal cubierto con tests\n"
                    "- Tests en CI sin flakiness\n"
                    "- Reporte de cobertura generado"
                ),
                "stack": ["TypeScript"],
            })
            orden += 1

    # ── INFRA ──────────────────────────────────────────────────────────────────
    if capas["infra"]:
        if complejidad == "compleja":
            tareas.append({
                "nombre": f"[Infra] Configurar ambientes para: {titulo}",
                "tipo": "Infra", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Infraestructura base para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:300]}\n\n"
                    "- Dockerfile multi-stage optimizado\n"
                    "- Variables de entorno por ambiente (dev/staging/prod)\n"
                    "- Health check que valide BD y dependencias críticas"
                ),
                "criterios": (
                    "- Imagen Docker construye sin errores\n"
                    "- Variables documentadas por ambiente\n"
                    "- Health check respondiendo 200"
                ),
                "stack": ["Docker"],
            })
            orden += 1
            tareas.append({
                "nombre": f"[Infra] Pipeline CI/CD y monitoreo para: {titulo}",
                "tipo": "Infra", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Pipeline y observabilidad para '{titulo}'.\n\n"
                    "- CI: lint + tests + build en cada PR\n"
                    "- CD: deploy automático a staging en merge a main\n"
                    "- Rollback en < 2 minutos\n"
                    "- Alertas: error rate > 1% o latencia p95 > 2s"
                ),
                "criterios": (
                    "- Pipeline CI verde en cada PR\n"
                    "- Deploy a staging automático\n"
                    "- Rollback probado y documentado en runbook\n"
                    "- Alertas configuradas"
                ),
                "stack": ["Docker"],
            })
            orden += 1
        else:
            tareas.append({
                "nombre": f"[Infra] Configurar deploy para: {titulo}",
                "tipo": "Infra", "orden": orden, "estimacion": "M",
                "descripcion": (
                    f"Pipeline CI/CD para '{titulo}'.\n\n"
                    f"Contexto: {descripcion[:300]}\n\n"
                    "- Dockerfile multi-stage\n"
                    "- Variables de entorno por ambiente\n"
                    "- Health check y rollback strategy"
                ),
                "criterios": (
                    "- Pipeline CI en cada PR\n"
                    "- Deploy automático a staging\n"
                    "- Rollback documentado en runbook"
                ),
                "stack": ["Docker"],
            })
            orden += 1

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
