import { Injectable } from '@angular/core';
import Feature from 'ol/Feature';
import GeoJSONFormat from 'ol/format/GeoJSON';
import LineString from 'ol/geom/LineString';
import Point from 'ol/geom/Point';
import Draw from 'ol/interaction/Draw';
import VectorLayer from 'ol/layer/Vector';
import Map from 'ol/Map';
import VectorSource from 'ol/source/Vector';
import { DrawMode } from './map-context.service';

@Injectable({
  providedIn: 'root'
})
export class MapDrawingService {
  private drawInteraction: Draw | null = null;
  private drawnSupportCoordinates: number[][] = [];

  updateDrawInteraction(
    map: Map,
    drawMode: DrawMode,
    drawLayer: VectorLayer<VectorSource> | undefined,
    supportLineLayer: VectorLayer<VectorSource> | undefined,
    onGeometryChange: (geometries: Record<string, any>[] | null) => void
  ): Draw | null {
    if (this.drawInteraction) {
      map.removeInteraction(this.drawInteraction);
      this.drawInteraction = null;
    }

    if (drawMode === 'none') {
      return null;
    }

    const drawSource = drawLayer?.getSource();

    if (!drawSource) {
      return null;
    }

    this.drawInteraction = new Draw({
      source: drawSource,
      type: 'Point'
    });

    this.drawInteraction.on('drawend', (event) => {
      const geometry = event.feature.getGeometry();

      if (!geometry || geometry.getType() !== 'Point') {
        onGeometryChange(null);
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

      this.updateDrawnSupportsTotal(drawLayer);
      this.updateTemporarySupportLine(supportLineLayer);

      onGeometryChange(this.getAllDrawnSupportGeometries(drawLayer));
    });

    map.addInteraction(this.drawInteraction);
    return this.drawInteraction;
  }

  clearDrawGeometry(
    drawLayer: VectorLayer<VectorSource> | undefined,
    supportLineLayer: VectorLayer<VectorSource> | undefined
  ): Record<string, any>[] {
    drawLayer?.getSource()?.clear();
    supportLineLayer?.getSource()?.clear();
    this.drawnSupportCoordinates = [];
    return [];
  }

  private getAllDrawnSupportGeometries(
    drawLayer: VectorLayer<VectorSource> | undefined
  ): Record<string, any>[] {
    const source = drawLayer?.getSource();

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

  private updateDrawnSupportsTotal(drawLayer: VectorLayer<VectorSource> | undefined): void {
    const source = drawLayer?.getSource();

    if (!source) {
      return;
    }

    const total = this.drawnSupportCoordinates.length;

    source.getFeatures().forEach(feature => {
      feature.set('support_total', total);
    });

    source.changed();
  }

  private updateTemporarySupportLine(
    supportLineLayer: VectorLayer<VectorSource> | undefined
  ): void {
    const source = supportLineLayer?.getSource();

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
}
