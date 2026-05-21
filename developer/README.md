# 👨‍💻 Developer Agent

Agente autónomo que toma tareas técnicas del backlog en Notion, implementa
el código en el proyecto correspondiente siguiendo las convenciones existentes,
y hace commit por tarea en un branch dedicado por idea.

## ¿Qué hace?

1. Lee el `CLAUDE.md` raíz (si existe) y los estándares de arquitectura
2. Lee las tareas en estado `Backlog` de Notion ordenadas por dependencia
3. Actualiza cada proyecto a `RAMA_BASE` antes de tocarlo
4. Crea un branch `feature/<idea>` por cada idea origen
5. Por cada tarea (respetando dependencias):
   - Verifica que las tareas prerequisito estén completadas
   - Lee el código existente o el estándar de arquitectura (proyecto nuevo)
   - Implementa siguiendo exactamente las convenciones/estándar
   - Si hay ambigüedad, deja un comentario en la tarea y continúa con otras
   - Hace commit con mensaje convencional referenciando la tarea
   - Marca la tarea como `QA` en Notion
6. Hace push del branch y deja un resumen en la idea origen

## Estructura

```
developer/
├── notion_tool.py        ← CRUD de Notion (leer tareas, comentar, actualizar estado)
├── developer_local.md    ← prompt del agente
├── run_agent.sh          ← script de arranque
├── .env.example          ← plantilla de variables
├── .gitignore
└── README.md
```

## Requisitos

- **Claude Code CLI** instalado: https://claude.ai/code
- **Python 3.8+**
- **Git** configurado con acceso al workspace
- Variables de entorno en `.env`

## Configuración

### 1. Crear integración en Notion
1. Ve a https://www.notion.so/my-integrations
2. New integration → `scrum-master-agent` → Internal
3. Copia el token → `NOTION_TOKEN` en `.env`
4. En el tablero **Tareas técnicas**: `...` → Connections → conecta la integración

### 2. Crear el archivo .env
```bash
cp .env.example .env
# Edita .env con tus valores reales
```

### 3. Asegúrate de que git está configurado
```bash
git config --global user.name "Developer Agent"
git config --global user.email "tu@email.com"
```

## Uso

```bash
# Procesar todas las tareas del backlog
./run_agent.sh

# Procesar máximo N tareas
./run_agent.sh 5
```

## Variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `NOTION_TOKEN` | ✅ | Token de integración interna de Notion |
| `NOTION_DB_TAREAS` | ✅ | ID del tablero de Tareas técnicas |
| `BASE_PATH` | ✅ | Ruta absoluta al workspace raíz |
| `RAMA_BASE` | ✅ | Rama git contra la que se actualizan los proyectos (ej: `main`) |
| `STANDARDS_DIR` | ❌ | Carpeta de estándares dentro de BASE_PATH (default: `_standards`) |
| `MAX_TAREAS_POR_EJECUCION` | ❌ | Límite de tareas por ejecución |

## Estándares de arquitectura

Al implementar un proyecto nuevo, el agente lee el archivo de estándar
correspondiente desde `BASE_PATH/_standards/` (o la carpeta configurada en
`STANDARDS_DIR`). El estándar define estructura de carpetas, convenciones
de código, patrones y reglas que el agente sigue estrictamente.

Si la tarea referencia un estándar en su descripción, el agente lo lee
y lo aplica. Si no hay estándar ni código previo como guía, el agente
deja un comentario pidiendo aclaración antes de implementar.

## Estrategia de branches y commits

```
main
└── feature/audit-log-multitenant
    ├── feat(db): diseñar esquema audit_logs          ← tarea 1
    ├── feat(backend): implementar interceptor         ← tarea 2
    └── feat(backend): modo almacenamiento local       ← tarea 3
```

## Comunicación con el Scrum Master

El agente deja comentarios en Notion en dos situaciones:

**En la tarea** — cuando hay ambigüedad o un bloqueo técnico:
```
🤖 Developer Agent: La descripción menciona "seguir el patrón de auth",
pero existen dos implementaciones distintas en auth-service y en api-gateway.
¿Cuál debe usarse como referencia?
```

**En la idea origen** — al terminar todas las tareas:
```
🤖 Developer Agent: Implementación completada.
Branch: feature/audit-log-multitenant
Tareas completadas: 4
Tareas bloqueadas: 1 (ver comentario en tarea [Test] QA e integración)
Pendiente: revisión de código y merge a main.
```