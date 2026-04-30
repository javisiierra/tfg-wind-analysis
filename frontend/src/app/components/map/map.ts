import {
  AfterViewInit,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  SimpleChanges
} from '@angular/core';

import Map from 'ol/Map';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import OSM from 'ol/source/OSM';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import GeoJSONFormat from 'ol/format/GeoJSON';
import { fromLonLat } from 'ol/proj';
import Draw from 'ol/interaction/Draw';
import { DrawMode } from '../../app';

import LineString from 'ol/geom/LineString';
import Point from 'ol/geom/Point';

import Style from 'ol/style/Style';
import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import CircleStyle from 'ol/style/Circle';
import Feature from 'ol/Feature';
import Geometry from 'ol/geom/Geometry';

@Component({
  selector: 'app-map',
  standalone: true,
  templateUrl: './map.html',
  styleUrl: './map.css'
})
export class MapComponent implements AfterViewInit, OnChanges {
  @Input() casePath: string = '';
  @Input() selectedLayer: string = '';
  @Input() drawMode: DrawMode = 'none';
  @Input() clearDrawToken = 0;

  @Output() geometryChange = new EventEmitter<Record<string, any>[] | null>();

  map: Map | undefined;

  vanosLayer: VectorLayer<VectorSource> | undefined;
  displayLayer: VectorLayer<VectorSource> | undefined;
  supportLineLayer: VectorLayer<VectorSource> | undefined;
  drawLayer: VectorLayer<VectorSource> | undefined;

  drawInteraction: Draw | null = null;

  private tooltipElement: HTMLElement | null = null;
  private currentTooltipLayer = '';
  private drawnSupportCoordinates: number[][] = [];

  ngAfterViewInit(): void {
    this.tooltipElement = document.getElementById('map-tooltip');

    this.vanosLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.getFeatureStyle(feature as Feature<Geometry>, 'vanos')
    });

    this.displayLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.getFeatureStyle(feature as Feature<Geometry>, this.selectedLayer)
    });

    this.supportLineLayer = new VectorLayer({
      source: new VectorSource(),
      style: new Style({
        stroke: new Stroke({
          color: '#16a34a',
          width: 3
        })
      })
    });

    this.drawLayer = new VectorLayer({
      source: new VectorSource(),
      style: new Style({
        image: new CircleStyle({
          radius: 7,
          fill: new Fill({ color: '#16a34a' }),
          stroke: new Stroke({ color: '#ffffff', width: 2 })
        })
      })
    });

    this.map = new Map({
      target: 'map',
      layers: [
        new TileLayer({
          source: new OSM()
        }),
        this.vanosLayer,
        this.displayLayer,
        this.supportLineLayer,
        this.drawLayer
      ],
      view: new View({
        center: fromLonLat([-5.85, 43.36]),
        zoom: 10
      })
    });

    this.registerTooltipEvents();
    this.updateDrawInteraction();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (
      changes['selectedLayer'] &&
      this.selectedLayer &&
      this.casePath &&
      this.displayLayer
    ) {
      this.loadSelectedLayer(this.selectedLayer, this.casePath);
    }

    if (changes['drawMode'] && this.map) {
      this.updateDrawInteraction();
    }

    if (changes['clearDrawToken'] && this.drawLayer) {
      this.clearDrawGeometry();
    }
  }

  private loadSelectedLayer(layerName: string, casePath: string): void {
    this.currentTooltipLayer = layerName;

    if (layerName === 'worst') {
      this.loadWorstSupportsWithGlobalIds(casePath);
      return;
    }

    this.vanosLayer?.getSource()?.clear();
    this.loadLayerIntoSource(layerName, casePath, this.displayLayer?.getSource(), true);
  }

  private async loadWorstSupportsWithGlobalIds(casePath: string): Promise<void> {
    try {
      const [vanosData, apoyosData, worstData] = await Promise.all([
        this.fetchLayerData('vanos', casePath),
        this.fetchLayerData('apoyos', casePath),
        this.fetchLayerData('worst', casePath)
      ]);

      const format = new GeoJSONFormat();

      const vanosFeatures = format.readFeatures(vanosData, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857'
      }) as Feature<Geometry>[];

      const apoyoFeatures = format.readFeatures(apoyosData, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857'
      }) as Feature<Geometry>[];

      const worstFeatures = format.readFeatures(worstData, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857'
      }) as Feature<Geometry>[];

      this.assignFallbackVanoIds(vanosFeatures);
      this.assignFallbackSupportIds(apoyoFeatures);
      this.assignWorstGlobalIdsFromSupports(worstFeatures, apoyoFeatures);

      this.vanosLayer?.getSource()?.clear();
      this.displayLayer?.getSource()?.clear();

      this.vanosLayer?.getSource()?.addFeatures(vanosFeatures);
      this.displayLayer?.getSource()?.addFeatures(worstFeatures);

      this.vanosLayer?.changed();
      this.displayLayer?.changed();

      const source = this.displayLayer?.getSource();

      if (source) {
        this.fitSource(source);
      }
    } catch (err) {
      console.error('Error cargando peores apoyos con IDs globales:', err);
    }
  }

  private fetchLayerData(layerName: string, casePath: string): Promise<any> {
    const endpoint = this.getLayerEndpoint(layerName);

    return fetch(`http://127.0.0.1:8000/api/v1/layers/${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ case_path: casePath })
    }).then(res => {
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      return res.json();
    });
  }

  private loadLayerIntoSource(
    layerName: string,
    casePath: string,
    source: VectorSource | undefined | null,
    fitToLayer: boolean
  ): void {
    const endpoint = this.getLayerEndpoint(layerName);

    if (!endpoint || !source) {
      console.warn(`Capa no soportada: ${layerName}`);
      return;
    }

    fetch(`http://127.0.0.1:8000/api/v1/layers/${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ case_path: casePath })
    })
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        return res.json();
      })
      .then(data => {
        const format = new GeoJSONFormat();

        const features = format.readFeatures(data, {
          dataProjection: 'EPSG:4326',
          featureProjection: 'EPSG:3857'
        }) as Feature<Geometry>[];

        this.assignFallbackIds(features, layerName);

        source.clear();

        if (!features.length) {
          console.warn(`La capa ${layerName} no contiene features.`);
          return;
        }

        source.addFeatures(features);

        this.displayLayer?.changed();
        this.vanosLayer?.changed();

        if (fitToLayer) {
          this.fitSource(source);
        }
      })
      .catch(err => {
        console.error(`Error cargando capa ${layerName}:`, err);
      });
  }

  private getLayerEndpoint(layerName: string): string {
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

  private assignFallbackIds(features: Feature<Geometry>[], layerName: string): void {
    if (layerName === 'apoyos') {
      this.assignFallbackSupportIds(features);
      return;
    }

    if (layerName === 'vanos') {
      this.assignFallbackVanoIds(features);
    }
  }

  private assignFallbackSupportIds(features: Feature<Geometry>[]): void {
  const pointFeatures = features.filter(feature => {
    const geometry = feature.getGeometry();
    return geometry?.getType() === 'Point';
  });

  pointFeatures.forEach((feature, index) => {
    const props = feature.getProperties();

    const order =
      props['sup_order'] ??
      props['SUP_ORDER'] ??
      props['support_order'] ??
      props['SUPPORT_ORDER'] ??
      props['support_or'] ??
      props['SUPPORT_OR'] ??
      props['generated_id'] ??
      index + 1;

    const total =
      props['sup_total'] ??
      props['SUP_TOTAL'] ??
      props['support_total'] ??
      props['SUPPORT_TOTAL'] ??
      props['support_to'] ??
      props['SUPPORT_TO'] ??
      pointFeatures.length;

    feature.set('support_order', Number(order));
    feature.set('support_total', Number(total));

    if (!feature.get('generated_id')) {
      feature.set('generated_id', Number(order));
    }
  });
}

  private assignWorstGlobalIdsFromSupports(
    worstFeatures: Feature<Geometry>[],
    apoyoFeatures: Feature<Geometry>[]
  ): void {
    const supports = apoyoFeatures.filter(feature => {
      return feature.getGeometry()?.getType() === 'Point';
    });

    const worstPoints = worstFeatures.filter(feature => {
      return feature.getGeometry()?.getType() === 'Point';
    });

    worstPoints.forEach(worst => {
      const worstExtent = worst.getGeometry()?.getExtent();

      if (!worstExtent) {
        return;
      }

      const worstX = (worstExtent[0] + worstExtent[2]) / 2;
      const worstY = (worstExtent[1] + worstExtent[3]) / 2;

      let nearestSupport: Feature<Geometry> | null = null;
      let minDistance = Infinity;

      supports.forEach(support => {
        const supportExtent = support.getGeometry()?.getExtent();

        if (!supportExtent) {
          return;
        }

        const supportX = (supportExtent[0] + supportExtent[2]) / 2;
        const supportY = (supportExtent[1] + supportExtent[3]) / 2;

        const distance = Math.sqrt(
          Math.pow(worstX - supportX, 2) +
          Math.pow(worstY - supportY, 2)
        );

        if (distance < minDistance) {
          minDistance = distance;
          nearestSupport = support;
        }
      });

      if (!nearestSupport) {
        console.warn('No se encontró apoyo cercano para un peor apoyo.');
        return;
      }

      const globalId = this.getFeatureIdentifier(nearestSupport);

      if (globalId !== null) {
        worst.set('global_support_id', globalId);
      }
    });
  }

  private assignFallbackVanoIds(features: Feature<Geometry>[]): void {
    const lineFeatures = features.filter(feature => {
      const type = feature.getGeometry()?.getType();
      return type === 'LineString' || type === 'MultiLineString';
    });

    lineFeatures.sort((a, b) => {
      const ax = a.getGeometry()?.getExtent()[0] ?? 0;
      const bx = b.getGeometry()?.getExtent()[0] ?? 0;
      return ax - bx;
    });

    lineFeatures.forEach((feature, index) => {
      if (!this.getFeatureIdentifier(feature)) {
        feature.set('generated_id', index + 1);
      }
    });
  }

  private getFeatureStyle(feature: Feature<Geometry>, layerName: string): Style {
    const geometryType = feature.getGeometry()?.getType();

    if (layerName === 'worst') {
      return new Style({
        image: new CircleStyle({
          radius: 8,
          fill: new Fill({ color: '#dc2626' }),
          stroke: new Stroke({ color: '#ffffff', width: 2 })
        })
      });
    }

    if (layerName === 'apoyos') {
      const order = feature.get('support_order');
      const total = feature.get('support_total');
      const isEndpoint = order === 1 || order === total;

      return new Style({
        image: new CircleStyle({
          radius: isEndpoint ? 8 : 5,
          fill: new Fill({ color: isEndpoint ? '#7c3aed' : '#16a34a' }),
          stroke: new Stroke({ color: '#ffffff', width: isEndpoint ? 2 : 1.5 })
        })
      });
    }

    if (layerName === 'vanos' || geometryType === 'LineString' || geometryType === 'MultiLineString') {
      return new Style({
        stroke: new Stroke({
          color: '#1d4ed8',
          width: 4
        })
      });
    }

    if (layerName === 'dominio' || geometryType === 'Polygon' || geometryType === 'MultiPolygon') {
      return new Style({
        stroke: new Stroke({
          color: '#f59e0b',
          width: 3
        }),
        fill: new Fill({
          color: 'rgba(245, 158, 11, 0.16)'
        })
      });
    }

    return new Style({
      image: new CircleStyle({
        radius: 5,
        fill: new Fill({ color: '#2563eb' }),
        stroke: new Stroke({ color: '#ffffff', width: 1.5 })
      })
    });
  }

  private registerTooltipEvents(): void {
    if (!this.map || !this.tooltipElement) {
      return;
    }

    this.map.on('pointermove', (event) => {
      if (!this.map || !this.tooltipElement) {
        return;
      }

      const feature = this.map.forEachFeatureAtPixel(
        event.pixel,
        (feat) => feat as Feature<Geometry>,
        { hitTolerance: 6 }
      );

      if (!feature) {
        this.tooltipElement.style.display = 'none';
        return;
      }

      const html = this.buildTooltipHtml(feature);

      if (!html) {
        this.tooltipElement.style.display = 'none';
        return;
      }

      this.tooltipElement.innerHTML = html;
      this.tooltipElement.style.display = 'block';
      this.tooltipElement.style.left = `${event.pixel[0] + 14}px`;
      this.tooltipElement.style.top = `${event.pixel[1] + 14}px`;
    });

    this.map.getViewport().addEventListener('mouseleave', () => {
      if (this.tooltipElement) {
        this.tooltipElement.style.display = 'none';
      }
    });
  }

  private buildTooltipHtml(feature: Feature<Geometry>): string {
    const geometryType = feature.getGeometry()?.getType();
    const id = this.getFeatureIdentifier(feature) ?? 'Sin identificador';

    if (geometryType === 'LineString' || geometryType === 'MultiLineString') {
      return `
        <strong>Vano / tramo</strong><br>
        Identificador: ${id}
      `;
    }

    if (this.currentTooltipLayer === 'worst') {
      const props = feature.getProperties();

      const risk =
        props['risk'] ??
        props['riesgo'] ??
        props['score'] ??
        props['max_speed'] ??
        props['velocidad_max'];

      const direction =
        props['direction'] ??
        props['direccion'] ??
        props['wind_dir'] ??
        props['direccion_viento'];

      return `
        <strong>Peor apoyo</strong><br>
        Apoyo general: ${id}<br>
        ${risk !== undefined ? `Valor crítico: ${risk}<br>` : ''}
        ${direction !== undefined ? `Dirección: ${direction}°<br>` : ''}
      `;
    }

    if (this.currentTooltipLayer === 'apoyos') {
      const order = feature.get('support_order');
      const total = feature.get('support_total');

      const endpointText =
        order === 1 ? '<br><strong>Inicio de línea</strong>' :
        order === total ? '<br><strong>Final de línea</strong>' :
        '';

      return `
        <strong>Apoyo</strong><br>
        Identificador: ${id}
        ${endpointText}
      `;
    }

    if (this.currentTooltipLayer === 'dominio') {
      return `<strong>Dominio de simulación</strong>`;
    }

    return '';
  }

  private getFeatureIdentifier(feature: Feature<Geometry>): string | number | null {
  const props = feature.getProperties();

  return (
    props['global_support_id'] ??
    props['id'] ??
    props['ID'] ??
    props['apoyo'] ??
    props['APOYO'] ??
    props['numero'] ??
    props['NUMERO'] ??
    props['n_apoyo'] ??
    props['N_APOYO'] ??
    props['cod_apoyo'] ??
    props['COD_APOYO'] ??
    props['support_id'] ??
    props['SUPPORT_ID'] ??
    props['support_order'] ??
    props['SUPPORT_ORDER'] ??
    props['sup_order'] ??
    props['SUP_ORDER'] ??
    props['global_id'] ??
    props['GLOBAL_ID'] ??
    props['name'] ??
    props['Name'] ??
    props['generated_id'] ??
    null
  );
}

  private fitSource(source: VectorSource): void {
    const extent = source.getExtent();

    if (
      extent &&
      this.map &&
      isFinite(extent[0]) &&
      isFinite(extent[1]) &&
      isFinite(extent[2]) &&
      isFinite(extent[3])
    ) {
      this.map.getView().fit(extent, {
        padding: [40, 40, 40, 40],
        maxZoom: 16,
        duration: 500
      });
    }
  }

  private updateDrawInteraction(): void {
    if (!this.map) {
      return;
    }

    if (this.drawInteraction) {
      this.map.removeInteraction(this.drawInteraction);
      this.drawInteraction = null;
    }

    if (this.drawMode === 'none') {
      return;
    }

    const drawSource = this.drawLayer?.getSource();

    if (!drawSource) {
      return;
    }

    this.drawInteraction = new Draw({
      source: drawSource,
      type: 'Point'
    });

    this.drawInteraction.on('drawend', (event) => {
      const geometry = event.feature.getGeometry();

      if (!geometry || geometry.getType() !== 'Point') {
        this.geometryChange.emit(null);
        return;
      }

      const pointGeometry = geometry as Point;
      const coordinate = pointGeometry.getCoordinates();

      this.drawnSupportCoordinates.push(coordinate);

      const supportOrder = this.drawnSupportCoordinates.length;
      const supportId = `AP-${supportOrder}`;

      event.feature.set('id', supportId);
      event.feature.set('tipo', 'apoyo');
      event.feature.set('support_order', supportOrder);
      event.feature.set('support_total', supportOrder);

      this.updateDrawnSupportsTotal();
      this.updateTemporarySupportLine();

      this.geometryChange.emit(this.getAllDrawnSupportGeometries());
    });

    this.map.addInteraction(this.drawInteraction);
  }

  private getAllDrawnSupportGeometries(): Record<string, any>[] {
    const source = this.drawLayer?.getSource();

    if (!source) {
      return [];
    }

    return source
      .getFeatures()
      .filter(feature => feature.getGeometry()?.getType() === 'Point')
      .map(feature => {
        const geometry = feature.getGeometry();

        return new GeoJSONFormat().writeGeometryObject(
          geometry!.clone().transform('EPSG:3857', 'EPSG:4326')
        ) as Record<string, any>;
      });
  }

  private updateDrawnSupportsTotal(): void {
    const source = this.drawLayer?.getSource();

    if (!source) {
      return;
    }

    const total = this.drawnSupportCoordinates.length;

    source.getFeatures().forEach(feature => {
      feature.set('support_total', total);
    });

    source.changed();
  }

  private updateTemporarySupportLine(): void {
    const source = this.supportLineLayer?.getSource();

    if (!source) {
      return;
    }

    source.clear();

    if (this.drawnSupportCoordinates.length < 2) {
      return;
    }

    const line = new Feature({
      geometry: new LineString(this.drawnSupportCoordinates)
    });

    source.addFeature(line);
  }

  private clearDrawGeometry(): void {
    this.drawLayer?.getSource()?.clear();
    this.supportLineLayer?.getSource()?.clear();
    this.drawnSupportCoordinates = [];
    this.geometryChange.emit([]);
  }
}