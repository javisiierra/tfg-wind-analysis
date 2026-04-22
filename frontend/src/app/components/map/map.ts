import { Component, Input, OnChanges, AfterViewInit, SimpleChanges } from '@angular/core';
import Map from 'ol/Map';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import OSM from 'ol/source/OSM';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import GeoJSON from 'ol/format/GeoJSON';
import { fromLonLat } from 'ol/proj';

@Component({
  selector: 'app-map',
  standalone: true,
  templateUrl: './map.html',
  styleUrl: './map.css'
})
export class MapComponent implements AfterViewInit, OnChanges {
  @Input() casePath: string = '';
  @Input() selectedLayer: string = '';

  map: Map | undefined;
  vectorLayer: VectorLayer<VectorSource> | undefined;

  ngAfterViewInit(): void {
    this.vectorLayer = new VectorLayer({
      source: new VectorSource()
    });

    this.map = new Map({
      target: 'map',
      layers: [
        new TileLayer({
          source: new OSM()
        }),
        this.vectorLayer
      ],
      view: new View({
        center: fromLonLat([-5.85, 43.36]),
        zoom: 10
      })
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (
      changes['selectedLayer'] &&
      this.selectedLayer &&
      this.casePath &&
      this.vectorLayer
    ) {
      this.loadLayer(this.selectedLayer, this.casePath);
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
        const format = new GeoJSON();
        const features = format.readFeatures(data, {
          dataProjection: 'EPSG:4326',
          featureProjection: 'EPSG:3857'
        });

        const source = this.vectorLayer?.getSource();
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
}