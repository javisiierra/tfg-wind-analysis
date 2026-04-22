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
import Draw, { createBox } from 'ol/interaction/Draw';
import { DrawMode } from '../../app';

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

  @Output() geometryChange = new EventEmitter<Record<string, any> | null>();

  map: Map | undefined;
  displayLayer: VectorLayer<VectorSource> | undefined;
  drawLayer: VectorLayer<VectorSource> | undefined;
  drawInteraction: Draw | null = null;

  ngAfterViewInit(): void {
    this.displayLayer = new VectorLayer({
      source: new VectorSource()
    });

    this.drawLayer = new VectorLayer({
      source: new VectorSource()
    });

    this.map = new Map({
      target: 'map',
      layers: [
        new TileLayer({
          source: new OSM()
        }),
        this.displayLayer,
        this.drawLayer
      ],
      view: new View({
        center: fromLonLat([-5.85, 43.36]),
        zoom: 10
      })
    });

    this.updateDrawInteraction();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (
      changes['selectedLayer'] &&
      this.selectedLayer &&
      this.casePath &&
      this.displayLayer
    ) {
      this.loadLayer(this.selectedLayer, this.casePath);
    }

    if (changes['drawMode'] && this.map) {
      this.updateDrawInteraction();
    }

    if (changes['clearDrawToken'] && this.drawLayer) {
      this.clearDrawGeometry();
    }
  }

  loadLayer(layerName: string, casePath: string): void {
    fetch(`http://127.0.0.1:8000/api/v1/layers/${layerName}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        case_path: casePath
      })
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
        });

        const source = this.displayLayer?.getSource();
        source?.clear();

        if (!features.length) {
          console.warn(`La capa ${layerName} no contiene features.`);
          return;
        }

        source?.addFeatures(features);

        const extent = source?.getExtent();
        if (
          extent &&
          this.map &&
          isFinite(extent[0]) &&
          isFinite(extent[1]) &&
          isFinite(extent[2]) &&
          isFinite(extent[3])
        ) {
          this.map.getView().fit(extent, {
            padding: [20, 20, 20, 20],
            maxZoom: 16,
            duration: 500
          });
        }
      })
      .catch(err => {
        console.error(`Error cargando capa ${layerName}:`, err);
      });
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
      type: this.drawMode === 'rectangle' ? 'Circle' : 'Polygon',
      geometryFunction: this.drawMode === 'rectangle' ? createBox() : undefined
    });

    this.drawInteraction.on('drawstart', () => {
      drawSource.clear();
    });

    this.drawInteraction.on('drawend', (event) => {
      const geometry = event.feature.getGeometry();
      if (!geometry) {
        this.geometryChange.emit(null);
        return;
      }

      const geojsonGeometry = new GeoJSONFormat().writeGeometryObject(
        geometry.clone().transform('EPSG:3857', 'EPSG:4326')
      ) as Record<string, any>;

      this.geometryChange.emit(geojsonGeometry);
      this.updateDrawInteraction();
    });

    this.map.addInteraction(this.drawInteraction);
  }

  private clearDrawGeometry(): void {
    this.drawLayer?.getSource()?.clear();
    this.geometryChange.emit(null);
  }
}
