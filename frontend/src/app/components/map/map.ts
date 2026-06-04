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
import { fromLonLat } from 'ol/proj';
import Draw from 'ol/interaction/Draw';
import Feature from 'ol/Feature';
import Geometry from 'ol/geom/Geometry';
import { DrawMode } from '../../services/map-context.service';
import { GisLayerService, MapLayerSet } from '../../services/gis-layer.service';
import { MapDrawingService } from '../../services/map-drawing.service';
import { MapStyleService } from '../../services/map-style.service';
import { MapTooltipService } from '../../services/map-tooltip.service';

@Component({
  selector: 'app-map',
  standalone: true,
  templateUrl: './map.html',
  styleUrl: './map.css',
  providers: [MapDrawingService]
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

  constructor(
    private readonly gisLayers: GisLayerService,
    private readonly drawing: MapDrawingService,
    private readonly styles: MapStyleService,
    private readonly tooltips: MapTooltipService
  ) {}

  ngAfterViewInit(): void {
    this.tooltipElement = document.getElementById('map-tooltip');
    this.createMapLayers();

    this.map = new Map({
      target: 'map',
      layers: [
        new TileLayer({
          source: new OSM()
        }),
        this.vanosLayer!,
        this.displayLayer!,
        this.criticalVanosAuxLayer!,
        this.criticalSupportsAuxLayer!,
        this.criticalSpansLayer!,
        this.supportLineLayer!,
        this.drawLayer!
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

  private createMapLayers(): void {
    this.vanosLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.styles.getFeatureStyle(feature as Feature<Geometry>, 'vanos')
    });
    this.vanosLayer.setZIndex(20);

    this.displayLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.styles.getFeatureStyle(feature as Feature<Geometry>, this.selectedLayer)
    });
    this.displayLayer.setZIndex(30);

    this.criticalVanosAuxLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.styles.getFeatureStyle(feature as Feature<Geometry>, 'vanos')
    });
    this.criticalVanosAuxLayer.setZIndex(20);

    this.criticalSupportsAuxLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.styles.getFeatureStyle(feature as Feature<Geometry>, 'apoyos')
    });
    this.criticalSupportsAuxLayer.setZIndex(30);

    this.criticalSpansLayer = new VectorLayer({
      source: new VectorSource(),
      style: (feature) => this.styles.getFeatureStyle(feature as Feature<Geometry>, 'worst')
    });
    this.criticalSpansLayer.setZIndex(50);

    this.supportLineLayer = new VectorLayer({
      source: new VectorSource(),
      style: this.styles.createSupportLineStyle()
    });
    this.supportLineLayer.setZIndex(35);

    this.drawLayer = new VectorLayer({
      source: new VectorSource(),
      style: this.styles.createDrawSupportStyle()
    });
    this.drawLayer.setZIndex(40);
  }

  private loadSelectedLayer(layerName: string, casePath: string): void {
    this.currentTooltipLayer = layerName;
    this.gisLayers.loadSelectedLayer(
      layerName,
      casePath,
      this.getLayerSet(),
      (source) => this.fitSource(source)
    );
  }

  private registerTooltipEvents(): void {
    if (!this.map || !this.tooltipElement) {
      return;
    }

    this.tooltips.registerTooltipEvents(
      this.map,
      this.tooltipElement,
      () => this.currentTooltipLayer
    );
  }

  private updateDrawInteraction(): void {
    if (!this.map) {
      return;
    }

    this.drawInteraction = this.drawing.updateDrawInteraction(
      this.map,
      this.drawMode,
      this.drawLayer,
      this.supportLineLayer,
      (geometries) => this.geometryChange.emit(geometries)
    );
  }

  private clearDrawGeometry(): void {
    const geometries = this.drawing.clearDrawGeometry(this.drawLayer, this.supportLineLayer);
    this.geometryChange.emit(geometries);
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

  private getLayerSet(): MapLayerSet {
    return {
      vanosLayer: this.vanosLayer,
      displayLayer: this.displayLayer,
      criticalVanosAuxLayer: this.criticalVanosAuxLayer,
      criticalSupportsAuxLayer: this.criticalSupportsAuxLayer,
      criticalSpansLayer: this.criticalSpansLayer
    };
  }
}
