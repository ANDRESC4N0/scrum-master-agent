# 🤖 AI Agents

Ecosistema de agentes autónomos para el ciclo de desarrollo de software.
Cada agente corre localmente con acceso al código y se comunica via Notion.

## Agentes

### 🧩 Scrum Master (`/scrum-master`)
Lee ideas de negocio en Notion, analiza el código existente y genera
tareas técnicas ordenadas para el equipo de desarrollo.

### 👨‍💻 Developer (`/developer`)
Lee las tareas del backlog en Notion, implementa el código en el proyecto
correspondiente y hace commit por tarea en un branch por idea.

## Flujo de colaboración

```
[Tú]  →  Escribes idea en Notion (campo Proyecto + descripción)
  ↓
[Scrum Master]  →  Analiza código + genera tareas técnicas en Notion
  ↓
[Developer]  →  Lee tareas → implementa → commit → push branch
  ↓
[Tú]  →  Revisas el PR y haces merge
```

## Comunicación entre agentes

Ambos agentes dejan comentarios en las tarjetas de Notion:
- **Scrum Master** → aclara criterios de aceptación o agrega contexto
- **Developer** → reporta bloqueos, dudas técnicas o decisiones tomadas

## Workspace y estándares de arquitectura

Los agentes trabajan sobre un directorio base (`BASE_PATH`) que puede estar
vacío o contener proyectos existentes. Ambos agentes buscan reglas de
arquitectura en una carpeta de estándares dentro de ese directorio.

### Estructura esperada del workspace

```
BASE_PATH/
├── CLAUDE.md               ← (opcional) Arquitectura global del ecosistema
├── _standards/             ← Reglas de arquitectura por stack/tipo
│   ├── golang_architecture_monolith.md
│   ├── golang_architecture_api.md
│   └── node_architecture_api.md
├── proyecto-a/             ← Proyecto existente
└── proyecto-b/             ← Proyecto existente
```

### Carpeta `_standards/`

Contiene archivos `.md` con reglas obligatorias de desarrollo. Cada archivo
define la estructura de carpetas, convenciones de código, patrones y reglas
para un stack + tipo de proyecto específico.

**Convención de nombre:** `<stack>_architecture_<tipo>.md`

Los agentes las usan así:
- **Scrum Master** — al generar tareas para un proyecto nuevo, referencia el
  estándar aplicable en la descripción de cada tarea
- **Developer** — al implementar un proyecto nuevo, sigue estrictamente
  las reglas del estándar referenciado

Si `CLAUDE.md` no existe y el workspace está vacío, los agentes dependen
enteramente de estos estándares para crear proyectos desde cero.

La carpeta se configura vía la variable `STANDARDS_DIR` (por defecto `_standards`).

## Configuración

Cada agente tiene su propio `.env` con sus variables específicas.
Ambos comparten `BASE_PATH`, `RAMA_BASE`, `STANDARDS_DIR` y `NOTION_TOKEN`.

## Ejecución

```bash
# Scrum Master — procesar ideas pendientes
./scrum-master/run_agent.sh

# Developer — ejecutar tareas del backlog
./developer/run_agent.sh

# Con límite
./scrum-master/run_agent.sh 2   # máximo 2 ideas
./developer/run_agent.sh 5      # máximo 5 tareas
```