import { Injectable } from '@angular/core';
import Feature from 'ol/Feature';
import Map from 'ol/Map';
import Geometry from 'ol/geom/Geometry';
import { GeoFeatureNormalizer } from './geo-feature-normalizer.service';

@Injectable({
  providedIn: 'root'
})
export class MapTooltipService {
  constructor(private readonly normalizer: GeoFeatureNormalizer) {}

  registerTooltipEvents(
    map: Map,
    tooltipElement: HTMLElement,
    getCurrentTooltipLayer: () => string
  ): void {
    map.on('pointermove', (event) => {
      const feature = map.forEachFeatureAtPixel(
        event.pixel,
        (feat) => feat as Feature<Geometry>,
        { hitTolerance: 6 }
      );

      if (!feature) {
        tooltipElement.style.display = 'none';
        return;
      }

      const html = this.buildTooltipHtml(feature, getCurrentTooltipLayer());

      if (!html) {
        tooltipElement.style.display = 'none';
        return;
      }

      tooltipElement.innerHTML = html;
      tooltipElement.style.display = 'block';
      tooltipElement.style.left = `${event.pixel[0] + 14}px`;
      tooltipElement.style.top = `${event.pixel[1] + 14}px`;
    });

    map.getViewport().addEventListener('mouseleave', () => {
      tooltipElement.style.display = 'none';
    });
  }

  buildTooltipHtml(feature: Feature<Geometry>, currentTooltipLayer: string): string {
    const geometryType = feature.getGeometry()?.getType();
    const id = this.normalizer.getFeatureIdentifier(feature) ?? 'Sin identificador';
    const tooltipLayer = feature.get('__tooltipLayer') ?? currentTooltipLayer;

    if (geometryType === 'LineString' || geometryType === 'MultiLineString') {
      const spanLabel = this.normalizer.getCriticalSpanLabel(feature.getProperties());
      return `
        <strong>Vano</strong><br>
        ${spanLabel !== undefined ? `Tramo: ${spanLabel}<br>` : `Identificador: ${id}`}
      `;
    }

    if (tooltipLayer === 'worst') {
      const props = feature.getProperties();
      const direction = props['direction_deg'] ?? props['wind_direction'];

      return `
        <strong>Vano crítico</strong><br>
        Tramo: ${this.normalizer.getCriticalSpanLabel(props) ?? id}<br>
        ${direction !== undefined ? `Dirección: ${this.formatNumber(direction)}°<br>` : ''}
        ${this.buildWindMetricsHtml(props)}
        ${this.buildCriticalReasonHtml(props)}
      `;
    }

    if (tooltipLayer === 'apoyos') {
      const order = feature.get('support_order');
      const total = feature.get('support_total');
      const endpointText =
        order === 1 ? '<br><strong>Inicio de línea</strong>' :
        order === total ? '<br><strong>Final de línea</strong>' :
        '';
      const spanLabel = this.normalizer.getCriticalSpanLabel(feature.getProperties());

      return `
        <strong>Apoyo</strong><br>
        Identificador: ${id}<br>
        ${order !== undefined ? `Orden: ${order}<br>` : ''}
        ${spanLabel !== undefined ? `Vano asociado: ${spanLabel}<br>` : ''}
        ${this.buildWindMetricsHtml(feature.getProperties())}
        ${endpointText}
      `;
    }

    if (tooltipLayer === 'dominio') {
      return `<strong>Dominio de simulación</strong>`;
    }

    return '';
  }

  private buildWindMetricsHtml(props: Record<string, any>): string {
    const windSpeed = props['wind_speed'];
    const vperpMin = props['critical_metric'];
    const relativeAngle = props['angle_relative'];

    return `
        ${windSpeed !== undefined ? `Velocidad viento: ${this.formatNumber(windSpeed)} m/s<br>` : ''}
        ${vperpMin !== undefined ? `Componente perpendicular mínima: ${this.formatNumber(vperpMin)} m/s<br>` : ''}
        ${relativeAngle !== undefined ? `Ángulo relativo: ${this.formatNumber(relativeAngle)}°<br>` : ''}
      `;
  }

  private buildCriticalReasonHtml(props: Record<string, any>): string {
    const reason = this.normalizer.pickProperty(props, ['critical_reason']);

    return reason !== undefined ? `Motivo: ${reason}<br>` : '';
  }

  private formatNumber(value: any): string {
    const numericValue = Number(value);

    if (!Number.isFinite(numericValue)) {
      return String(value);
    }

    return numericValue.toFixed(2);
  }
}
