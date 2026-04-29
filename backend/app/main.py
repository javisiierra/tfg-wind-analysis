from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router

app = FastAPI(
    title="TFG WindNinja WebGIS API",
    description=(
        "API para crear casos, gestionar apoyos, preparar entradas "
        "geoespaciales y ejecutar el pipeline de WindNinja."
    ),
    version="1.0.0",
    openapi_tags=[
        {
            "name": "Sistema",
            "description": "Comprobaciones generales de disponibilidad de la API.",
        },
        {
            "name": "Dominio",
            "description": "Creación del dominio de simulación y generación de DEM y meteorología.",
        },
        {
            "name": "Apoyos",
            "description": "Gestión manual de apoyos dibujados desde la interfaz WebGIS.",
        },
        {
            "name": "Pipeline",
            "description": "Ejecución de procesos principales: WindNinja, renombrado y rosa de vientos.",
        },
        {
            "name": "Estado",
            "description": "Validación del estado del caso y comprobación de entradas disponibles.",
        },
        {
            "name": "Capas",
            "description": "Consulta de capas geoespaciales para visualización en el mapa.",
        },
        {
            "name": "Análisis",
            "description": "Procesos de postprocesado y cálculo de peores apoyos.",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # para desarrollo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)