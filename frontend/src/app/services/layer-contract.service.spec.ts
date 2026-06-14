import { describe, expect, it } from 'vitest';

import { normalizeLayerGeoJson } from './layer-contract.service';

describe('normalizeLayerGeoJson', () => {
  it('adapts legacy SHP support aliases at the HTTP boundary', () => {
    const result = normalizeLayerGeoJson('apoyos', {
      type: 'FeatureCollection',
      features: [{ properties: { id: '7', sup_order: 7, sup_total: 9 } }]
    });

    expect(result.features[0].properties).toMatchObject({
      id: 'AP-7',
      support_order: 7,
      support_total: 9
    });
  });

  it('adapts legacy worst-support aliases to the canonical contract', () => {
    const result = normalizeLayerGeoJson('worst', {
      type: 'FeatureCollection',
      features: [{
        properties: {
          from_ap: 'AP-1',
          to_ap: 'AP-2',
          vperp_min: 1.2,
          w_speed: 8.4,
          w_dir: 270,
          alpha: 15
        }
      }]
    });

    expect(result.features[0].properties).toMatchObject({
      from_support: 'AP-1',
      to_support: 'AP-2',
      span_label: 'AP-1 -> AP-2',
      critical_metric: 1.2,
      wind_speed: 8.4,
      wind_direction: 270,
      angle_relative: 15
    });
  });
});
