import { Injectable } from '@angular/core';
import Feature from 'ol/Feature';
import Geometry from 'ol/geom/Geometry';
import CircleStyle from 'ol/style/Circle';
import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import Style from 'ol/style/Style';

@Injectable({
  providedIn: 'root'
})
export class MapStyleService {
  getFeatureStyle(feature: Feature<Geometry>, layerName: string): Style {
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

  createSupportLineStyle(): Style {
    return new Style({
      stroke: new Stroke({
        color: '#16a34a',
        width: 3
      })
    });
  }

  createDrawSupportStyle(): Style {
    return new Style({
      image: new CircleStyle({
        radius: 7,
        fill: new Fill({ color: '#16a34a' }),
        stroke: new Stroke({ color: '#ffffff', width: 2 })
      })
    });
  }

  getLayerZIndex(layerName: string): number {
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
}
