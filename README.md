# 🤖 Scrum Master Agent

Agente autónomo que lee ideas de negocio en Notion y genera tareas técnicas ordenadas para el equipo de desarrollo.

## Variables de entorno requeridas

Todas las credenciales e IDs van en el entorno `scrum-master-env` de Claude Code (o en un archivo `.env` local). **Nunca las subas al repositorio.**

```env
# Token de la integración interna de Notion
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxx

# IDs de las bases de datos (sin guiones, solo el UUID)
NOTION_DB_EPICAS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DB_IDEAS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DB_TAREAS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Configuración inicial

### 1. Crear integración en Notion

1. Ve a [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Clic en **+ New integration** → nombre `scrum-master-agent` → tipo **Internal**
3. Copia el **Internal Integration Secret** (`secret_...`) → va en `NOTION_TOKEN`

### 2. Obtener los IDs de los tableros

Abre cada tablero en Notion y copia el UUID de la URL:
```
https://www.notion.so/<workspace>/<ESTE-ES-EL-ID>?v=...
```

### 3. Dar acceso a los tableros

En cada tablero (Épicas, Ideas, Tareas técnicas):
- Clic en `...` → **Connections** → conecta `scrum-master-agent`

### 4. Configurar variables en Claude Code

En el entorno `scrum-master-env` agrega las cuatro variables del bloque de arriba.

### 5. Prompt de la rutina

```
Ejecuta el siguiente comando y reporta el resultado:

python3 scrum_master.py
```

## Uso local

```bash
cp .env.example .env
# Edita .env con tus valores reales
source .env && python3 scrum_master.py
```

## Archivo .env.example

```env
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxx
NOTION_DB_EPICAS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DB_IDEAS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_DB_TAREAS=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Flujo

```
🏔️ Épica  →  📋 Idea (Pendiente)  →  🛠️ Tareas técnicas (Backlog)
```

1. Escribe una idea en el tablero **Ideas de negocio** con estado `Pendiente`
2. El agente la descompone: DB → Backend → Frontend → Test (→ Infra si aplica)
3. La idea pasa automáticamente a `En progreso`
