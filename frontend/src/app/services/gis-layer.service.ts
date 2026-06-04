import { Injectable } from '@angular/core';
import Feature from 'ol/Feature';
import GeoJSONFormat from 'ol/format/GeoJSON';
import Geometry from 'ol/geom/Geometry';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import { environment } from '../../environments/environment';
import { normalizeLayerGeoJson } from './layer-contract.service';
import { GeoFeatureNormalizer } from './geo-feature-normalizer.service';
import { MapStyleService } from './map-style.service';

export type MapLayerSet = {
  vanosLayer: VectorLayer<VectorSource> | undefined;
  displayLayer: VectorLayer<VectorSource> | undefined;
  criticalVanosAuxLayer: VectorLayer<VectorSource> | undefined;
  criticalSupportsAuxLayer: VectorLayer<VectorSource> | undefined;
  criticalSpansLayer: VectorLayer<VectorSource> | undefined;
};

@Injectable({
  providedIn: 'root'
})
export class GisLayerService {
  private readonly apiUrl = environment.apiUrl;

  constructor(
    private readonly normalizer: GeoFeatureNormalizer,
    private readonly styles: MapStyleService
  ) {}

  loadSelectedLayer(
    layerName: string,
    casePath: string,
    layers: MapLayerSet,
    fitSource: (source: VectorSource) => void
  ): void {
    layers.displayLayer?.setZIndex(this.styles.getLayerZIndex(layerName));

    if (layerName === 'worst') {
      void this.loadCriticalSpansComposite(casePath, layers, fitSource);
      return;
    }

    this.clearCriticalCompositeLayers(layers);

    if (layerName === 'apoyos') {
      layers.vanosLayer?.getSource()?.clear();
      void this.loadApoyosWithWorstMetrics(casePath, layers, fitSource);
      return;
    }

    layers.vanosLayer?.getSource()?.clear();
    void this.loadLayerIntoSource(layerName, casePath, layers.displayLayer?.getSource(), true, layers, fitSource);
  }

  async loadApoyosWithWorstMetrics(
    casePath: string,
    layers: MapLayerSet,
    fitSource: (source: VectorSource) => void
  ): Promise<void> {
    try {
      const apoyosData = await this.fetchLayerData('apoyos', casePath);
      const apoyoFeatures = this.readFeatures(apoyosData);

      this.normalizer.assignFallbackSupportIds(apoyoFeatures);

      try {
        const worstData = await this.fetchLayerData('worst', casePath);
        const worstFeatures = this.readFeatures(worstData);

        this.normalizer.assignWorstGlobalIdsFromSupports(worstFeatures, apoyoFeatures);
        this.normalizer.assignWorstMetricsToSupports(apoyoFeatures, worstFeatures);
      } catch (err) {
        console.info('No hay metricas de vanos criticos disponibles para enriquecer apoyos:', err);
      }

      layers.displayLayer?.getSource()?.clear();

      if (!apoyoFeatures.length) {
        console.warn('La capa apoyos no contiene features.');
        return;
      }

      layers.displayLayer?.getSource()?.addFeatures(apoyoFeatures);
      layers.displayLayer?.changed();

      const source = layers.displayLayer?.getSource();
      if (source) {
        fitSource(source);
      }
    } catch (err) {
      console.error('Error cargando apoyos:', err);
    }
  }

  async loadCriticalSpansComposite(
    casePath: string,
    layers: MapLayerSet,
    fitSource: (source: VectorSource) => void
  ): Promise<void> {
    layers.vanosLayer?.getSource()?.clear();
    layers.displayLayer?.getSource()?.clear();
    this.clearCriticalCompositeLayers(layers);

    let apoyoFeatures: Feature<Geometry>[] = [];

    try {
      const apoyosData = await this.fetchLayerData('apoyos', casePath);
      apoyoFeatures = this.readFeatures(apoyosData);
      this.normalizer.assignFallbackSupportIds(apoyoFeatures);
      apoyoFeatures.forEach(feature => feature.set('__tooltipLayer', 'apoyos'));
      layers.criticalSupportsAuxLayer?.getSource()?.addFeatures(apoyoFeatures);
    } catch (err) {
      console.warn('No se pudieron cargar apoyos auxiliares para vanos criticos:', err);
    }

    try {
      const vanosData = await this.fetchLayerData('vanos', casePath);
      const vanoFeatures = this.readFeatures(vanosData);
      this.normalizer.assignFallbackVanoIds(vanoFeatures);
      vanoFeatures.forEach(feature => feature.set('__tooltipLayer', 'vanos'));
      layers.criticalVanosAuxLayer?.getSource()?.addFeatures(vanoFeatures);
    } catch (err) {
      console.warn('No se pudieron cargar vanos auxiliares para vanos criticos:', err);
    }

    try {
      const worstData = await this.fetchLayerData('worst', casePath);
      const worstFeatures = this.readFeatures(worstData);

      worstFeatures.forEach(feature => feature.set('__tooltipLayer', 'worst'));
      if (apoyoFeatures.length) {
        this.normalizer.assignWorstGlobalIdsFromSupports(worstFeatures, apoyoFeatures);
      }

      layers.criticalSpansLayer?.getSource()?.addFeatures(worstFeatures);

      layers.criticalVanosAuxLayer?.changed();
      layers.criticalSupportsAuxLayer?.changed();
      layers.criticalSpansLayer?.changed();

      const source = layers.criticalSpansLayer?.getSource();

      if (source) {
        fitSource(source);
      }
    } catch (err) {
      console.error('Error cargando vanos criticos con IDs globales:', err);
    }
  }

  clearCriticalCompositeLayers(layers: MapLayerSet): void {
    layers.criticalVanosAuxLayer?.getSource()?.clear();
    layers.criticalSupportsAuxLayer?.getSource()?.clear();
    layers.criticalSpansLayer?.getSource()?.clear();
    layers.criticalVanosAuxLayer?.changed();
    layers.criticalSupportsAuxLayer?.changed();
    layers.criticalSpansLayer?.changed();
  }

  fetchLayerData(layerName: string, casePath: string): Promise<any> {
    const endpoint = this.getLayerEndpoint(layerName);

    return fetch(`${this.apiUrl}/layers/${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ case_path: casePath })
    }).then(res => {
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      return res.json().then(data => normalizeLayerGeoJson(layerName, data));
    });
  }

  async loadLayerIntoSource(
    layerName: string,
    casePath: string,
    source: VectorSource | undefined | null,
    fitToLayer: boolean,
    layers: MapLayerSet,
    fitSource: (source: VectorSource) => void
  ): Promise<void> {
    const endpoint = this.getLayerEndpoint(layerName);

    if (!endpoint || !source) {
      console.warn(`Capa no soportada: ${layerName}`);
      return;
    }

    try {
      const data = await this.fetchLayerData(layerName, casePath);
      const features = this.readFeatures(data);

      this.normalizer.assignFallbackIds(features, layerName);

      source.clear();

      if (!features.length) {
        console.warn(`La capa ${layerName} no contiene features.`);
        return;
      }

      source.addFeatures(features);

      layers.displayLayer?.changed();
      layers.vanosLayer?.changed();

      if (fitToLayer) {
        fitSource(source);
      }
    } catch (err) {
      console.error(`Error cargando capa ${layerName}:`, err);
    }
  }

  getLayerEndpoint(layerName: string): string {
    switch (layerName) {
      case 'worst':
        return 'worst-supports';
      case 'apoyos':
        return 'apoyos';
      case 'vanos':
        return 'vanos';
      case 'dominio':
        return 'dominio';
      default:
        return layerName;
    }
  }

  private readFeatures(data: any): Feature<Geometry>[] {
    return new GeoJSONFormat().readFeatures(data, {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857'
    }) as Feature<Geometry>[];
  }
}
