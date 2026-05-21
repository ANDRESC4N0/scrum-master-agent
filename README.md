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

## Configuración

Cada agente tiene su propio `.env` con sus variables específicas.
Ambos comparten `BASE_PATH` y `NOTION_TOKEN`.

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