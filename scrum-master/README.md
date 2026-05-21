# 🤖 Scrum Master Agent — Local

Agente que corre en tu máquina, lee tu código real y genera tareas técnicas
específicas para cada proyecto referenciando archivos, patrones y convenciones existentes.

## Arquitectura

```
BASE_PATH/
├── CLAUDE.md                  ← (opcional) arquitectura global del ecosistema
├── _standards/                ← reglas de arquitectura por stack/tipo
│   ├── golang_architecture_monolith.md
│   └── node_architecture_api.md
├── backoffice/                ← proyecto existente
│   ├── CLAUDE.md o README.md
│   └── ...código
├── auth-service/              ← proyecto existente
└── ai-agents/                 ← este repositorio
    └── scrum-master/
        ├── notion_tool.py         ← CRUD de Notion
        ├── scrum_master_local.md  ← prompt del agente
        ├── run_agent.sh           ← script de arranque
        └── .env                   ← credenciales (no subir a git)
```

### Estándares de arquitectura (`_standards/`)

Los archivos `.md` en esta carpeta definen reglas obligatorias para crear
proyectos nuevos. El agente identifica el stack y tipo de proyecto de la idea,
busca el estándar correspondiente y genera tareas que lo referencian.

Si `CLAUDE.md` no existe y el workspace está vacío, el agente depende de estos
estándares para saber cómo estructurar un proyecto nuevo.

**Convención de nombre:** `<stack>_architecture_<tipo>.md`

## Requisitos

- **Claude Code CLI** instalado: https://claude.ai/code
- **Python 3.8+**
- **Variables de entorno** configuradas en `.env`

## Configuración

### 1. Clonar este repo dentro de tu workspace
```bash
cd C:/documentos/work
git clone https://github.com/ANDRESC4N0/scrum-master-agent
```

### 2. Crear el archivo .env
```bash
cp scrum-master-agent/.env.example scrum-master-agent/.env
# Edita .env con tus valores reales
```

### 3. Crear integración en Notion
1. Ve a https://www.notion.so/my-integrations
2. New integration → `scrum-master-agent` → Internal
3. Copia el token → NOTION_TOKEN en .env
4. En cada tablero: `...` → Connections → conecta la integración

## Uso

```bash
# Procesar todas las ideas pendientes
cd C:/documentos/work
./scrum-master-agent/run_agent.sh

# Procesar máximo N ideas
./scrum-master-agent/run_agent.sh 2
```

## Qué genera el agente

Para una idea como *"Agregar feature de exportación de reportes en backoffice"*:

```
[Backend] Agregar handler ExportarReportes en backoffice/internal/handlers/reportes.go
  → Sigue el patrón de handlers/usuarios.go, usa el middleware de auth existente

[DB] Agregar query GetReportesPaginados en backoffice/internal/repository/reporte_repo.go
  → Extiende la interfaz ReporteRepository con el nuevo método

[Frontend] Crear componente ExportButton en backoffice/web/src/components/Reportes/
  → Sigue el patrón de components/Usuarios/ExportButton.tsx si existe

[Test] Tests unitarios para ExportarReportes en backoffice/internal/handlers/reportes_test.go
  → Sigue el patrón de tests existente en el proyecto
```

## Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| NOTION_TOKEN | ✅ | Token de integración interna de Notion |
| NOTION_DB_EPICAS | ✅ | ID de la base de datos de Épicas |
| NOTION_DB_IDEAS | ✅ | ID de la base de datos de Ideas |
| NOTION_DB_TAREAS | ✅ | ID de la base de datos de Tareas técnicas |
| BASE_PATH | ✅ | Ruta absoluta al workspace raíz |
| RAMA_BASE | ✅ | Rama git contra la que se validan los proyectos (ej: `main`) |
| STANDARDS_DIR | ❌ | Carpeta de estándares dentro de BASE_PATH (default: `_standards`) |
| MAX_IDEAS_POR_EJECUCION | ❌ | Límite de ideas por ejecución (sin límite si no se define) |
