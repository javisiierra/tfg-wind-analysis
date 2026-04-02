# TFG - Wind Analysis Web Platform

Aplicación web para el análisis de viento sobre líneas eléctricas mediante simulación con WindNinja, combinando procesamiento geoespacial en FastAPI y visualización interactiva en Angular + OpenLayers.

---

## Descripción

Este proyecto permite:

- Procesar datos geoespaciales de una línea eléctrica
- Generar modelos de terreno (DEM)
- Ejecutar simulaciones de viento con WindNinja
- Analizar resultados (wind rose, perfil longitudinal, etc.)
- Visualizar todo en un mapa interactivo web

El sistema está diseñado para funcionar a partir de una carpeta de caso, donde se encuentran todos los datos necesarios.

---

## Arquitectura

El proyecto está dividido en dos partes principales:

backend/   → API FastAPI + pipeline de procesamiento  
frontend/  → Aplicación Angular + visualización web  

---

## Requisitos

Backend:
- Python 3.10+
- FastAPI
- GeoPandas
- WindNinja

Frontend:
- Node.js
- Angular CLI

---

## Ejecución

Backend:
cd backend
uvicorn app.main:app --reload

Frontend:
cd frontend
ng serve

---

## Uso básico

1. Introducir ruta del caso:
C:\TFG\datos\Corredoria_Grado_1_y_2

2. Ejecutar fases desde la interfaz

3. Visualizar capas en el mapa

---

## Estado

Versión 1.0.0 - Base funcional

---

## Autor

Trabajo Fin de Grado (TFG) -- Javier Sierra
