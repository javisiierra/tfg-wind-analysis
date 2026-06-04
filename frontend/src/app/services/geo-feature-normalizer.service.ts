import { Injectable } from '@angular/core';
import Feature from 'ol/Feature';
import Geometry from 'ol/geom/Geometry';

@Injectable({
  providedIn: 'root'
})
export class GeoFeatureNormalizer {
  assignFallbackIds(features: Feature<Geometry>[], layerName: string): void {
    if (layerName === 'apoyos') {
      this.assignFallbackSupportIds(features);
      return;
    }

    if (layerName === 'vanos') {
      this.assignFallbackVanoIds(features);
    }
  }

  assignFallbackSupportIds(features: Feature<Geometry>[]): void {
    const pointFeatures = features.filter(feature => {
      const geometry = feature.getGeometry();
      return geometry?.getType() === 'Point';
    });

    pointFeatures.forEach((feature, index) => {
      const props = feature.getProperties();
      const order = props['support_order'] ?? props['generated_id'] ?? index + 1;
      const total = props['support_total'] ?? pointFeatures.length;

      feature.set('support_order', Number(order));
      feature.set('support_total', Number(total));

      if (!feature.get('generated_id')) {
        feature.set('generated_id', Number(order));
      }
    });
  }

  assignFallbackVanoIds(features: Feature<Geometry>[]): void {
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

  assignWorstGlobalIdsFromSupports(
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
      const nearestSupport = this.findNearestPointFeature(worst, supports);

      if (!nearestSupport) {
        console.warn('No se encontro apoyo cercano para un peor apoyo.');
        return;
      }

      const globalId = this.getFeatureIdentifier(nearestSupport);

      if (globalId !== null) {
        worst.set('global_support_id', globalId);
      }
    });
  }

  assignWorstMetricsToSupports(
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

  getFeatureIdentifier(feature: Feature<Geometry>): string | number | null {
    const props = feature.getProperties();

    return (
      props['global_support_id'] ??
      props['id'] ??
      props['support_order'] ??
      props['generated_id'] ??
      null
    );
  }

  getCriticalSpanLabel(props: Record<string, any>): string | undefined {
    const explicitLabel = this.pickProperty(props, ['associated_span_label', 'span_label']);
    if (explicitLabel !== undefined) {
      return String(explicitLabel).replace(' -> ', ' &rarr; ');
    }

    const fromSupport = props['from_support'];
    const toSupport = props['to_support'];

    if (fromSupport !== undefined && toSupport !== undefined) {
      return `${fromSupport} &rarr; ${toSupport}`;
    }

    const mat = this.pickProperty(props, ['MAT', 'mat']);
    if (mat !== undefined) {
      return String(mat);
    }

    const fallbackId = this.pickProperty(props, ['global_support_id', 'id']);
    return fallbackId !== undefined ? String(fallbackId) : undefined;
  }

  pickProperty(props: Record<string, any>, names: string[]): any {
    for (const name of names) {
      const value = props[name];

      if (value !== undefined && value !== null && value !== '') {
        return value;
      }
    }

    return undefined;
  }

  private getSupportMatchKeys(feature: Feature<Geometry>): string[] {
    const props = feature.getProperties();
    const keys = [
      this.getFeatureIdentifier(feature),
      this.pickProperty(props, ['global_support_id', 'id']),
      this.pickProperty(props, ['support_order'])
    ];

    return this.uniqueNonEmptyKeys(keys);
  }

  private getWorstSupportMatchKeys(feature: Feature<Geometry>): string[] {
    const props = feature.getProperties();
    const keys = [
      this.pickProperty(props, ['from_support']),
      this.pickProperty(props, ['to_support']),
      this.pickProperty(props, ['from_order']),
      this.pickProperty(props, ['to_order']),
      this.pickProperty(props, ['global_support_id', 'id'])
    ];

    return this.uniqueNonEmptyKeys(keys);
  }

  private uniqueNonEmptyKeys(values: any[]): string[] {
    return [...new Set(values
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
      'wind_speed',
      'critical_metric',
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
    const value = props['critical_metric'];
    const numericValue = Number(value);

    return Number.isFinite(numericValue) ? numericValue : undefined;
  }

  private copyWorstMetric(from: Feature<Geometry>, to: Feature<Geometry>, key: string): void {
    const value = from.get(key);

    if (value !== undefined && value !== null && value !== '') {
      to.set(key, value);
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
}
