# TFG - Wind Analysis Web Platform

Aplicación web para el análisis de viento sobre líneas eléctricas mediante simulación con WindNinja, combinando procesamiento geoespacial en FastAPI y visualización interactiva en Angular + OpenLayers.

---

## Descripción

Este proyecto permite:

- Procesar datos geoespaciales de una línea eléctrica.
- Generar modelos de terreno (DEM).
- Ejecutar simulaciones de viento con WindNinja.
- Analizar resultados (wind rose, perfil longitudinal, spans y apoyos críticos).
- Consultar y procesar series meteorológicas ERA5 (descarga + análisis).
- Visualizar todo en un mapa interactivo web.

El sistema está diseñado para funcionar a partir de una carpeta de caso, donde se encuentran todos los datos necesarios.

---

## Arquitectura

El proyecto está dividido en dos partes principales:

- `backend/` → API FastAPI + pipeline de procesamiento + servicios ERA5.
- `frontend/` → Aplicación Angular + visualización web.

---

## Requisitos

### Backend

- Python 3.10+
- Dependencias Python en `backend/requirements.txt`
- WindNinja instalado y disponible en el sistema

Instalación:

```bash
cd backend
pip install -r requirements.txt
```

### Frontend

- Node.js 18+
- Angular CLI

Instalación:

```bash
cd frontend
npm install
```

---

## Configuración ERA5 (Copernicus CDS)

Para usar las funcionalidades ERA5 del backend necesitas credenciales de Copernicus CDS (`cdsapi`).

En Windows, crea el archivo:

`C:\Users\<usuario>\.cdsapirc`

Con contenido equivalente a:

```text
url: https://cds.climate.copernicus.eu/api
key: <uid>:<api-key>
```

También puedes configurar variables de entorno (`CDSAPI_URL`, `CDSAPI_KEY`), pero la forma recomendada para desarrollo local sigue siendo `.cdsapirc`.

---

## Ejecución

### Backend

```bash
cd backend
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
ng serve
```

### Docker

Para levantar el backend y el frontend en contenedores:

```bash
docker compose up --build
```

Servicios publicados:

- Frontend Angular: `http://localhost:4200`
- Backend FastAPI: `http://localhost:8000`
- Documentación API: `http://localhost:8000/docs`

Para parar el entorno:

```bash
docker compose down
```

Si necesitas credenciales ERA5, copia `.env.example` a `.env` y completa:

```bash
CDSAPI_URL=https://cds.climate.copernicus.eu/api
CDSAPI_KEY=<uid>:<api-key>
```

Nota sobre WindNinja: el backend queda preparado para leer el ejecutable desde la variable `WINDNINJA_CLI`. La imagen no instala WindNinja automáticamente, así que las fases que ejecutan WindNinja requieren añadirlo a la imagen o usar una imagen base que ya lo incluya.

---

## Uso básico

1. Introducir ruta del caso (ejemplo):
   `C:\TFG\datos\Corredoria_Grado_1_y_2`
2. Ejecutar fases desde la interfaz.
3. Visualizar capas y resultados en el mapa/dashboard.

---

## Rutas API: Dashboard vs Pipeline

- **Dashboard-only** (`/api/v1/dashboard/*`):
  - `POST /api/v1/dashboard/meteo-summary`
  - `POST /api/v1/dashboard/wind-timeseries`
  - `POST /api/v1/dashboard/wind-rose`

- **Pipeline WindNinja** (`/api/v1/*` en `pipeline.py`):
  - Endpoints de importación de caso, generación de dominio, DEM, apoyos, escenarios y ejecución WindNinja.
  - Se mantienen separados de dashboard para no introducir cambios funcionales directos en el flujo crítico de WindNinja.

---

## Estado

Versión 1.1.0 - Backend reproducible con `requirements.txt` y documentación ERA5 actualizada.

---

## Autor

Trabajo Fin de Grado (TFG) -- Javier Sierra
