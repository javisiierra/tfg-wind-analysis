# TFG - Wind Analysis Web Platform

Aplicacion web para el analisis de viento sobre lineas electricas mediante simulacion con WindNinja, combinando procesamiento geoespacial en FastAPI y visualizacion interactiva en Angular + OpenLayers.

---

## Descripcion

Este proyecto permite:

- Procesar datos geoespaciales de una linea electrica.
- Generar modelos de terreno (DEM).
- Ejecutar simulaciones de viento con WindNinja.
- Analizar resultados: wind rose, perfil longitudinal, spans y apoyos criticos.
- Consultar y procesar series meteorologicas ERA5.
- Visualizar todo en un mapa interactivo web.

El sistema funciona a partir de una carpeta de caso, donde se encuentran todos los datos necesarios.

---

## Arquitectura

El proyecto esta dividido en dos partes principales:

- `backend/`: API FastAPI + pipeline de procesamiento + servicios ERA5.
- `frontend/`: aplicacion Angular + visualizacion web.

---

## Requisitos

- Docker Desktop.
- Una carpeta local con los casos del proyecto.

El flujo soportado del proyecto es Docker Compose. No se mantiene como flujo principal la ejecucion local separada de backend y frontend.

---

## Configuracion

El despliegue local se configura con un archivo `.env`. Crea una copia de `.env.example`:

```bash
cp .env.example .env
```

En Windows tambien puedes copiarlo desde el explorador o con PowerShell:

```powershell
Copy-Item .env.example .env
```

### Variables `.env`

Para el funcionamiento completo del proyecto, configura todas estas variables en `.env`:

| Variable | Uso | Obligatoria |
| --- | --- | --- |
| `HOST_CASES_ROOT` | Carpeta local de tu ordenador que Docker monta como `/data` dentro del backend. | Si |
| `CDSAPI_URL` / `CDSAPI_KEY` | Credenciales de Copernicus CDS para funcionalidades ERA5. | Si |
| `CUSTOM_SRTM_API_KEY` | API key de OpenTopography para descargar DEM SRTM con `fetch_dem`. | Si |
| `WINDNINJA_CLI` | Nombre o ruta Linux del ejecutable WindNinja dentro del contenedor. Normalmente se deja como `WindNinja_cli`. | Si |

Si alguna variable falta o esta vacia, la aplicacion puede arrancar, pero fallara la fase que dependa de ella.

### Carpeta de casos

Edita `HOST_CASES_ROOT` en `.env` para indicar donde estan los casos en tu ordenador:

```env
HOST_CASES_ROOT=C:/Ruta/A/Tus/Casos
```

Cada persona puede usar su propia ruta local, por ejemplo:

```env
HOST_CASES_ROOT=D:\TFG\Casos
```

Dentro del contenedor esa carpeta siempre se monta como:

```text
/data
```

Por eso la aplicacion usa rutas internas como:

```text
/data/NombreDelCaso
```

### ERA5

Para usar las funcionalidades ERA5 del backend necesitas credenciales de Copernicus CDS (`cdsapi`). Configuralas en `.env`:

```env
CDSAPI_URL=https://cds.climate.copernicus.eu/api
CDSAPI_KEY=<uid>:<api-key>
```

### DEM SRTM

La fase `Generar DEM` (`POST /api/v1/domain/generate-dem`) descarga el modelo de elevacion SRTM usando `fetch_dem --src srtm`. Para que esa descarga funcione es necesaria una API key de OpenTopography.

Crea una cuenta o genera la clave en OpenTopography y añadela al archivo `.env`:

```env
CUSTOM_SRTM_API_KEY=<opentopography-api-key>
```

El backend pasa esta variable al ejecutable `fetch_dem` dentro del contenedor. Si falta o esta vacia, la generacion del DEM fallara al intentar descargar SRTM.

Despues de crear o modificar `.env`, reinicia los contenedores para que Docker Compose cargue las variables.

---

## Despliegue local con Docker Compose

El flujo soportado del proyecto es Docker Compose. No se mantiene como flujo principal la ejecucion local separada de backend y frontend.

### Modo recomendado con WindNinja

Usa este modo para levantar el proyecto completo. Es el despliegue recomendado porque WindNinja es una parte central del flujo de analisis y las fases principales dependen de `WindNinja_cli` o `fetch_dem` dentro del backend:

```bash
docker compose -f docker-compose.yml -f docker-compose.windninja.yml up --build
```

Este comando usa `backend/Dockerfile.windninja`, que compila WindNinja `3.12.1` en una version minima de `WindNinja_cli`, sin GUI y sin NinjaFOAM/OpenFOAM. Esta imagen tambien incluye `fetch_dem`, necesario para la descarga DEM SRTM.

Servicios publicados:

- Frontend Angular: `http://localhost:4200`
- Backend FastAPI: `http://localhost:8000`
- Documentacion API: `http://localhost:8000/docs`

El backend lee el ejecutable desde `WINDNINJA_CLI`. Con esta imagen normalmente debes dejar:

```env
WINDNINJA_CLI=WindNinja_cli
```

La instalacion de Windows, por ejemplo `C:/WindNinja/WindNinja-3.12.1/bin/WindNinja_cli.exe`, no se puede ejecutar directamente desde el contenedor Linux.

### Modo base sin WindNinja

Este modo solo sirve para pruebas parciales del backend/frontend que no ejecuten el pipeline completo de viento:

```bash
docker compose up --build
```

No es el despliegue recomendado para usar la aplicacion completa.

### Parar el entorno

Para detener y eliminar los contenedores:

```bash
docker compose down
```

Si has levantado el modo recomendado con WindNinja, puedes usar el mismo comando anterior desde la raiz del proyecto.

---

## Flujo recomendado

1. Copia `.env.example` a `.env`.
2. Configura `HOST_CASES_ROOT` con la carpeta local donde estan los casos.
3. Configura `CDSAPI_URL` y `CDSAPI_KEY` para las consultas ERA5.
4. Configura `CUSTOM_SRTM_API_KEY` para la descarga DEM SRTM.
5. Levanta el modo recomendado con WindNinja: `docker compose -f docker-compose.yml -f docker-compose.windninja.yml up --build`.
6. Abre la interfaz en `http://localhost:4200`.

---

## Uso basico

1. Selecciona un caso desde la interfaz.
2. Ejecuta las fases desde la interfaz.
3. Visualiza capas y resultados en el mapa/dashboard.

---

## Rutas API

- Dashboard:
  - `POST /api/v1/dashboard/meteo-summary`
  - `POST /api/v1/dashboard/wind-timeseries`
  - `POST /api/v1/dashboard/wind-rose`

- Pipeline WindNinja:
  - `POST /api/v1/case/import-folder`
  - `POST /api/v1/case/status`
  - `POST /api/v1/domain/generate-from-supports`
  - `POST /api/v1/domain/generate-dem`
  - `POST /api/v1/domain/generate-weather`
  - `POST /api/v1/pipeline/run-windninja`

---

## Estado

Version 1.2.0 - Entorno Docker reproducible para backend y frontend.

---

## Autor

Trabajo Fin de Grado (TFG) -- Javier Sierra
