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
import { DrawMode } from '../../services/map-context.service';

import LineString from 'ol/geom/LineString';
import Point from 'ol/geom/Point';

import Style from 'ol/style/Style';
import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import CircleStyle from 'ol/style/Circle';
import Feature from 'ol/Feature';
import Geometry from 'ol/geom/Geometry';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-map',
  standalone: true,
  templateUrl: './map.html',
  styleUrl: './map.css'
})
export class MapComponent implements AfterViewInit, OnChanges {
  @Input() casePath: string = '';
  @Input() selectedLayer: string = '';
  @Input() layerReloadToken = 0;
  @Input() drawMode: DrawMode = 'none';
  @Input() clearDrawToken = 0;
  @Input() layerRefreshToken = 0;

  @Output() geometryChange = new EventEmitter<Record<string, any>[] | null>();

  map: Map | undefined;

  vanosLayer: VectorLayer<VectorSource> | undefined;
  displayLayer: VectorLayer<VectorSource> | undefined;
  criticalVanosAuxLayer: VectorLayer<VectorSource> | undefined;
  criticalSupportsAuxLayer: VectorLayer<VectorSource> | undefined;
  criticalSpansLayer: VectorLayer<VectorSource> | undefined;
  supportLineLayer: VectorLayer<VectorSource> | undefined;
  drawLayer: VectorLayer<VectorSource> | undefined;

  drawInteraction: Draw | null = null;

  private tooltipElement: HTMLElement | null = null;
  private currentTooltipLayer = '';
  private drawnSupportCoordinates: number[][] = [];
  private readonly apiUrl = environment.apiUrl;

  ngAfterViewInit(): void {
    this.tooltipElement = document.getElementById('map-tooltip');

    this.vanosLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.getFeatureStyle(feature as Feature<Geometry>, 'vanos')
    });
    this.vanosLayer.setZIndex(20);

    this.displayLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.getFeatureStyle(feature as Feature<Geometry>, this.selectedLayer)
    });
    this.displayLayer.setZIndex(30);

    this.criticalVanosAuxLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.getFeatureStyle(feature as Feature<Geometry>, 'vanos')
    });
    this.criticalVanosAuxLayer.setZIndex(20);

    this.criticalSupportsAuxLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.getFeatureStyle(feature as Feature<Geometry>, 'apoyos')
    });
    this.criticalSupportsAuxLayer.setZIndex(30);

    this.criticalSpansLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.getFeatureStyle(feature as Feature<Geometry>, 'worst')
    });
    this.criticalSpansLayer.setZIndex(50);

    this.supportLineLayer = new VectorLayer({
      source: new VectorSource(),
      style: new Style({
        stroke: new Stroke({
          color: '#16a34a',
          width: 3
        })
      })
    });
    this.supportLineLayer.setZIndex(35);

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
    this.drawLayer.setZIndex(40);

    this.map = new Map({
      target: 'map',
      layers: [
        new TileLayer({
          source: new OSM()
        }),
        this.vanosLayer,
        this.displayLayer,
        this.criticalVanosAuxLayer,
        this.criticalSupportsAuxLayer,
        this.criticalSpansLayer,
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
      (changes['selectedLayer'] || changes['layerReloadToken']) &&
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

    if (
      changes['layerRefreshToken'] &&
      this.selectedLayer &&
      this.casePath &&
      this.displayLayer
    ) {
      this.loadSelectedLayer(this.selectedLayer, this.casePath);
    }
  }

  private loadSelectedLayer(layerName: string, casePath: string): void {
    this.currentTooltipLayer = layerName;
    this.displayLayer?.setZIndex(this.getLayerZIndex(layerName));

    if (layerName === 'worst') {
      this.loadCriticalSpansComposite(casePath);
      return;
    }

    this.clearCriticalCompositeLayers();

    if (layerName === 'apoyos') {
      this.vanosLayer?.getSource()?.clear();
      this.loadApoyosWithWorstMetrics(casePath);
      return;
    }

    this.vanosLayer?.getSource()?.clear();
    this.loadLayerIntoSource(layerName, casePath, this.displayLayer?.getSource(), true);
  }

  private async loadApoyosWithWorstMetrics(casePath: string): Promise<void> {
    try {
      const apoyosData = await this.fetchLayerData('apoyos', casePath);
      const format = new GeoJSONFormat();
      const apoyoFeatures = format.readFeatures(apoyosData, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857'
      }) as Feature<Geometry>[];

      this.assignFallbackSupportIds(apoyoFeatures);

      try {
        const worstData = await this.fetchLayerData('worst', casePath);
        const worstFeatures = format.readFeatures(worstData, {
          dataProjection: 'EPSG:4326',
          featureProjection: 'EPSG:3857'
        }) as Feature<Geometry>[];

        this.assignWorstGlobalIdsFromSupports(worstFeatures, apoyoFeatures);
        this.assignWorstMetricsToSupports(apoyoFeatures, worstFeatures);
      } catch (err) {
        console.info('No hay metricas de vanos criticos disponibles para enriquecer apoyos:', err);
      }

      this.displayLayer?.getSource()?.clear();

      if (!apoyoFeatures.length) {
        console.warn('La capa apoyos no contiene features.');
        return;
      }

      this.displayLayer?.getSource()?.addFeatures(apoyoFeatures);
      this.displayLayer?.changed();

      const source = this.displayLayer?.getSource();
      if (source) {
        this.fitSource(source);
      }
    } catch (err) {
      console.error('Error cargando apoyos:', err);
    }
  }

  private async loadCriticalSpansComposite(casePath: string): Promise<void> {
    this.vanosLayer?.getSource()?.clear();
    this.displayLayer?.getSource()?.clear();
    this.clearCriticalCompositeLayers();

    const format = new GeoJSONFormat();
    let apoyoFeatures: Feature<Geometry>[] = [];

    try {
      const apoyosData = await this.fetchLayerData('apoyos', casePath);
      apoyoFeatures = format.readFeatures(apoyosData, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857'
      }) as Feature<Geometry>[];
      this.assignFallbackSupportIds(apoyoFeatures);
      apoyoFeatures.forEach(feature => feature.set('__tooltipLayer', 'apoyos'));
      this.criticalSupportsAuxLayer?.getSource()?.addFeatures(apoyoFeatures);
    } catch (err) {
      console.warn('No se pudieron cargar apoyos auxiliares para vanos criticos:', err);
    }

    try {
      const vanosData = await this.fetchLayerData('vanos', casePath);
      const vanoFeatures = format.readFeatures(vanosData, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857'
      }) as Feature<Geometry>[];
      this.assignFallbackVanoIds(vanoFeatures);
      vanoFeatures.forEach(feature => feature.set('__tooltipLayer', 'vanos'));
      this.criticalVanosAuxLayer?.getSource()?.addFeatures(vanoFeatures);
    } catch (err) {
      console.warn('No se pudieron cargar vanos auxiliares para vanos criticos:', err);
    }

    try {
      const worstData = await this.fetchLayerData('worst', casePath);
      const worstFeatures = format.readFeatures(worstData, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857'
      }) as Feature<Geometry>[];

      worstFeatures.forEach(feature => feature.set('__tooltipLayer', 'worst'));
      if (apoyoFeatures.length) {
        this.assignWorstGlobalIdsFromSupports(worstFeatures, apoyoFeatures);
      }

      this.criticalSpansLayer?.getSource()?.addFeatures(worstFeatures);

      this.criticalVanosAuxLayer?.changed();
      this.criticalSupportsAuxLayer?.changed();
      this.criticalSpansLayer?.changed();

      const source = this.criticalSpansLayer?.getSource();

      if (source) {
        this.fitSource(source);
      }
    } catch (err) {
      console.error('Error cargando vanos criticos con IDs globales:', err);
    }
  }

  private clearCriticalCompositeLayers(): void {
    this.criticalVanosAuxLayer?.getSource()?.clear();
    this.criticalSupportsAuxLayer?.getSource()?.clear();
    this.criticalSpansLayer?.getSource()?.clear();
    this.criticalVanosAuxLayer?.changed();
    this.criticalSupportsAuxLayer?.changed();
    this.criticalSpansLayer?.changed();
  }

  private fetchLayerData(layerName: string, casePath: string): Promise<any> {
    const endpoint = this.getLayerEndpoint(layerName);

    return fetch(`${this.apiUrl}/layers/${endpoint}`, {
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

    fetch(`${this.apiUrl}/layers/${endpoint}`, {
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

  private assignWorstMetricsToSupports(
    apoyoFeatures: Feature<Geometry>[],
    worstFeatures: Feature<Geometry>[]
  ): void {
    const supportsByKey = new globalThis.Map<string, Feature<Geometry>>();

    apoyoFeatures.forEach(support => {
      this.getSupportMatchKeys(support).forEach(key => supportsByKey.set(key, support));
    });

    worstFeatures.forEach(worst => {
      const matchedSupports = this.getWorstSupportMatchKeys(worst)
        .map(key => supportsByKey.get(key))
        .filter((support): support is Feature<Geometry> => support !== undefined);

      if (!matchedSupports.length) {
        const nearestSupport = this.findNearestPointFeature(worst, apoyoFeatures);
        if (nearestSupport) {
          matchedSupports.push(nearestSupport);
        }
      }

      matchedSupports.forEach(support => {
        this.copyWorstMetricsIfMoreCritical(worst, support);
      });
    });
  }

  private getSupportMatchKeys(feature: Feature<Geometry>): string[] {
    const props = feature.getProperties();
    const keys = [
      this.getFeatureIdentifier(feature),
      this.pickProperty(props, ['global_support_id', 'generated_id', 'id', 'ID', 'MAT']),
      this.pickProperty(props, ['support_order', 'SUPPORT_ORDER', 'sup_order', 'SUP_ORDER'])
    ];

    return [...new Set(keys
      .filter(value => value !== undefined && value !== null && value !== '')
      .map(value => String(value)))];
  }

  private getWorstSupportMatchKeys(feature: Feature<Geometry>): string[] {
    const props = feature.getProperties();
    const keys = [
      this.pickProperty(props, ['from_support', 'from_support_id', 'from_ap']),
      this.pickProperty(props, ['to_support', 'to_support_id', 'to_ap']),
      this.pickProperty(props, ['from_order', 'from_idx']),
      this.pickProperty(props, ['to_order', 'to_idx']),
      this.pickProperty(props, ['global_support_id', 'generated_id', 'id', 'ID', 'MAT'])
    ];

    return [...new Set(keys
      .filter(value => value !== undefined && value !== null && value !== '')
      .map(value => String(value)))];
  }

  private copyWorstMetricsIfMoreCritical(from: Feature<Geometry>, to: Feature<Geometry>): void {
    const incomingMetric = this.extractCriticalMetric(from.getProperties());
    const existingMetric = this.extractCriticalMetric(to.getProperties());

    if (
      incomingMetric !== undefined &&
      existingMetric !== undefined &&
      incomingMetric >= existingMetric
    ) {
      return;
    }

    [
      'w_speed',
      'wind_speed',
      'vperp_min',
      'critical_metric',
      'alpha',
      'angle_relative',
      'critical_reason',
      'from_support',
      'to_support',
      'from_order',
      'to_order',
      'span_label',
      'MAT'
    ].forEach(key => this.copyWorstMetric(from, to, key));

    const spanLabel = this.getCriticalSpanLabel(from.getProperties());
    if (spanLabel) {
      to.set('associated_span_label', spanLabel);
    }
  }

  private extractCriticalMetric(props: Record<string, any>): number | undefined {
    const value = this.pickProperty(props, ['critical_metric', 'vperp_min', 'v_perp', 'componente_perpendicular']);
    const numericValue = Number(value);

    return Number.isFinite(numericValue) ? numericValue : undefined;
  }

  private getCriticalSpanLabel(props: Record<string, any>): string | undefined {
    const explicitLabel = this.pickProperty(props, ['associated_span_label', 'span_label', 'span_labe']);
    if (explicitLabel !== undefined) {
      return String(explicitLabel).replace(' -> ', ' &rarr; ');
    }

    const fromSupport = this.pickProperty(props, ['from_support', 'from_support_id', 'from_ap']);
    const toSupport = this.pickProperty(props, ['to_support', 'to_support_id', 'to_ap']);

    if (fromSupport !== undefined && toSupport !== undefined) {
      return `${fromSupport} &rarr; ${toSupport}`;
    }

    const mat = this.pickProperty(props, ['MAT', 'mat']);
    if (mat !== undefined) {
      return String(mat);
    }

    const fallbackId = this.pickProperty(props, ['global_support_id', 'generated_id', 'id', 'ID']);
    return fallbackId !== undefined ? String(fallbackId) : undefined;
  }
  private copyWorstMetric(from: Feature<Geometry>, to: Feature<Geometry>, key: string): void {
    const value = from.get(key);

    if (value !== undefined && value !== null && value !== '') {
      to.set(key, value);
    }
  }

  private getLayerZIndex(layerName: string): number {
    switch (layerName) {
      case 'dominio':
        return 10;
      case 'vanos':
        return 20;
      case 'apoyos':
        return 30;
      case 'worst':
        return 50;
      default:
        return 30;
    }
  }

  private findNearestPointFeature(
    target: Feature<Geometry>,
    candidates: Feature<Geometry>[]
  ): Feature<Geometry> | undefined {
    const targetExtent = target.getGeometry()?.getExtent();

    if (!targetExtent) {
      return undefined;
    }

    const targetX = (targetExtent[0] + targetExtent[2]) / 2;
    const targetY = (targetExtent[1] + targetExtent[3]) / 2;
    let nearest: Feature<Geometry> | undefined;
    let minDistance = Infinity;

    candidates.forEach(candidate => {
      const candidateExtent = candidate.getGeometry()?.getExtent();

      if (!candidateExtent) {
        return;
      }

      const candidateX = (candidateExtent[0] + candidateExtent[2]) / 2;
      const candidateY = (candidateExtent[1] + candidateExtent[3]) / 2;
      const distance = Math.sqrt(
        Math.pow(targetX - candidateX, 2) +
        Math.pow(targetY - candidateY, 2)
      );

      if (distance < minDistance) {
        minDistance = distance;
        nearest = candidate;
      }
    });

    return nearest;
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
    const tooltipLayer = feature.get('__tooltipLayer') ?? this.currentTooltipLayer;

    if (geometryType === 'LineString' || geometryType === 'MultiLineString') {
      const spanLabel = this.getCriticalSpanLabel(feature.getProperties());
      return `
        <strong>Vano</strong><br>
        ${spanLabel !== undefined ? `Tramo: ${spanLabel}<br>` : `Identificador: ${id}`}
      `;
    }

    if (tooltipLayer === 'worst') {
      const props = feature.getProperties();
      const direction = this.pickProperty(props, [
        'direction',
        'direccion',
        'wind_direction',
        'w_dir',
        'wind_dir',
        'direccion_viento'
      ]);

      return `
        <strong>Vano cr&iacute;tico</strong><br>
        Tramo: ${this.getCriticalSpanLabel(props) ?? id}<br>
        ${direction !== undefined ? `Direcci&oacute;n: ${this.formatNumber(direction)}&deg;<br>` : ''}
        ${this.buildWindMetricsHtml(props)}
      `;
    }

    if (tooltipLayer === 'apoyos') {
      const order = feature.get('support_order');
      const total = feature.get('support_total');
      const endpointText =
        order === 1 ? '<br><strong>Inicio de l&iacute;nea</strong>' :
        order === total ? '<br><strong>Final de l&iacute;nea</strong>' :
        '';

      return `
        <strong>Apoyo</strong><br>
        Identificador: ${id}<br>
        ${order !== undefined ? `Orden: ${order}<br>` : ''}
        ${this.getCriticalSpanLabel(feature.getProperties()) !== undefined ? `Vano asociado: ${this.getCriticalSpanLabel(feature.getProperties())}<br>` : ''}
        ${this.buildWindMetricsHtml(feature.getProperties())}
        ${endpointText}
      `;
    }

    if (tooltipLayer === 'dominio') {
      return `<strong>Dominio de simulaci&oacute;n</strong>`;
    }

    return '';
  }

  private buildWindMetricsHtml(props: Record<string, any>): string {
    const windSpeed = this.pickProperty(props, ['wind_speed', 'w_speed']);
    const vperpMin = this.pickProperty(props, ['critical_metric', 'vperp_min', 'v_perp']);
    const relativeAngle = this.pickProperty(props, ['angle_relative', 'alpha', 'alpha_eff']);
    const reason = this.pickProperty(props, ['critical_reason']);

    return `
        ${windSpeed !== undefined ? `Velocidad viento: ${this.formatNumber(windSpeed)} m/s<br>` : ''}
        ${vperpMin !== undefined ? `Componente perpendicular m&iacute;nima: ${this.formatNumber(vperpMin)} m/s<br>` : ''}
        ${relativeAngle !== undefined ? `&Aacute;ngulo relativo: ${this.formatNumber(relativeAngle)}&deg;<br>` : ''}
        ${reason !== undefined ? `Motivo: ${reason}<br>` : ''}
      `;
  }
  private pickProperty(props: Record<string, any>, names: string[]): any {
    for (const name of names) {
      const value = props[name];

      if (value !== undefined && value !== null && value !== '') {
        return value;
      }
    }

    return undefined;
  }

  private formatNumber(value: any): string {
    const numericValue = Number(value);

    if (!Number.isFinite(numericValue)) {
      return String(value);
    }

    return numericValue.toFixed(2);
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
