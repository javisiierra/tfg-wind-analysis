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

### Carpeta de casos

Crea un archivo `.env` a partir de `.env.example` e indica donde estan los casos en tu ordenador:

```env
HOST_CASES_ROOT=C:/Datos_TFG
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

Crea una cuenta o genera la clave en OpenTopography y anadela al archivo `.env`:

```env
CUSTOM_SRTM_API_KEY=<opentopography-api-key>
```

El backend pasa esta variable al ejecutable `fetch_dem` dentro del contenedor. Si falta o esta vacia, la generacion del DEM fallara al intentar descargar SRTM.

Despues de crear o modificar `.env`, reinicia los contenedores para que Docker Compose cargue la variable:

```bash
docker compose -f docker-compose.yml -f docker-compose.windninja.yml up --build
```

### WindNinja

El backend lee el ejecutable desde la variable `WINDNINJA_CLI`.

La imagen no instala WindNinja automaticamente. Las fases que ejecutan WindNinja requieren anadir WindNinja para Linux a la imagen backend o usar una imagen base que ya lo incluya.

La instalacion de Windows, por ejemplo `C:/WindNinja/WindNinja-3.12.1/bin/WindNinja_cli.exe`, no se puede ejecutar directamente desde el contenedor Linux.

Para construir el entorno con WindNinja dentro del backend:

```bash
docker compose -f docker-compose.yml -f docker-compose.windninja.yml up --build
```

Esta imagen compila WindNinja `3.12.1` en una version minima de `WindNinja_cli`, sin GUI y sin NinjaFOAM/OpenFOAM, porque el proyecto usa `initialization_method = pointInitialization` y salida ASCII. Para desarrollo normal sin ejecutar WindNinja puedes seguir usando:

```bash
docker compose up --build
```

---

## Ejecucion

Para levantar el backend y el frontend:

```bash
docker compose up --build
```

Servicios publicados:

- Frontend Angular: `http://localhost:4200`
- Backend FastAPI: `http://localhost:8000`
- Documentacion API: `http://localhost:8000/docs`

Para parar el entorno:

```bash
docker compose down
```

---

## Uso basico

1. Configura `HOST_CASES_ROOT` en `.env` apuntando a la carpeta local donde estan los casos.
2. Levanta la aplicacion con `docker compose up --build`.
3. Selecciona un caso desde la interfaz.
4. Ejecuta las fases desde la interfaz.
5. Visualiza capas y resultados en el mapa/dashboard.

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

Version 1.1.0 - Entorno Docker reproducible para backend y frontend.

---

## Autor

Trabajo Fin de Grado (TFG) -- Javier Sierra
