import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SimpleChange } from '@angular/core';
import Feature from 'ol/Feature';
import Point from 'ol/geom/Point';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MapComponent } from './map';
import { GisLayerService, MapLayerSet } from '../../services/gis-layer.service';
import { MapStyleService } from '../../services/map-style.service';
import { MapTooltipService } from '../../services/map-tooltip.service';

describe('MapComponent', () => {
  let component: MapComponent;
  let fixture: ComponentFixture<MapComponent>;
  let gisLayers: GisLayerService;
  let styles: MapStyleService;
  let tooltips: MapTooltipService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MapComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(MapComponent);
    component = fixture.componentInstance;
    gisLayers = TestBed.inject(GisLayerService);
    styles = TestBed.inject(MapStyleService);
    tooltips = TestBed.inject(MapTooltipService);
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should delegate selected layer loading when inputs change', () => {
    component.displayLayer = new VectorLayer({ source: new VectorSource() });
    component.selectedLayer = 'vanos';
    component.casePath = 'C:/case';
    const loadSpy = vi.spyOn(gisLayers, 'loadSelectedLayer').mockImplementation(() => {});

    component.ngOnChanges({
      selectedLayer: new SimpleChange('', 'vanos', false)
    });

    expect(loadSpy).toHaveBeenCalledWith(
      'vanos',
      'C:/case',
      expect.objectContaining({ displayLayer: component.displayLayer }),
      expect.any(Function)
    );
  });

  it('should not fail when unsupported layer is requested', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    await gisLayers.loadLayerIntoSource(
      'invalid',
      '/tmp',
      undefined,
      true,
      createLayerSet(),
      () => {}
    );

    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it('should render WindNinja metrics in worst support tooltip', () => {
    const feature = new Feature({
      geometry: new Point([0, 0]),
      global_support_id: 'AP-6',
      direction_deg: 250.74085312139727,
      wind_speed: 8.567,
      critical_metric: 1.234,
      angle_relative: 12.345,
      from_support: 'AP-5',
      to_support: 'AP-6',
      critical_reason: 'Menor componente perpendicular sobre el vano entre escenarios WindNinja',
    });

    const html = tooltips.buildTooltipHtml(feature, 'worst');

    expect(html).toContain('Vano cr&iacute;tico');
    expect(html).toContain('Tramo: AP-5 &rarr; AP-6');
    expect(html).toContain('Direcci&oacute;n: 250.74&deg;');
    expect(html).toContain('Velocidad viento: 8.57 m/s');
    expect(html).toContain('Componente perpendicular m&iacute;nima: 1.23 m/s');
    expect(html).toContain('&Aacute;ngulo relativo: 12.35&deg;');
    expect(html).toContain('Motivo: Menor componente perpendicular sobre el vano entre escenarios WindNinja');
  });

  it('should render worst-support metrics in support tooltip when present', () => {
    const feature = new Feature({
      geometry: new Point([0, 0]),
      id: 'AP-6',
      support_order: 6,
      support_total: 10,
      wind_speed: 8.567,
      critical_metric: 1.234,
      angle_relative: 12.345,
      associated_span_label: 'AP-5 &rarr; AP-6',
      critical_reason: 'Menor componente perpendicular sobre el vano entre escenarios WindNinja',
    });

    const html = tooltips.buildTooltipHtml(feature, 'apoyos');

    expect(html).toContain('Identificador: AP-6');
    expect(html).toContain('Orden: 6');
    expect(html).toContain('Vano asociado: AP-5 &rarr; AP-6');
    expect(html).toContain('Velocidad viento: 8.57 m/s');
    expect(html).toContain('Componente perpendicular m&iacute;nima: 1.23 m/s');
    expect(html).toContain('&Aacute;ngulo relativo: 12.35&deg;');
    expect(html).not.toContain('Motivo:');
  });

  it('should keep critical spans above supports by zIndex', () => {
    expect(styles.getLayerZIndex('worst')).toBeGreaterThan(styles.getLayerZIndex('apoyos'));
    (globalThis as any).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
    component.ngAfterViewInit();
    expect(component.criticalVanosAuxLayer?.getZIndex()).toBe(20);
    expect(component.criticalSupportsAuxLayer?.getZIndex()).toBe(30);
    expect(component.criticalSpansLayer?.getZIndex()).toBe(50);
  });

  it('should render critical spans with auxiliary supports and vanos when worst layer is selected', async () => {
    const layers = createLayerSet();

    const apoyos = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { id: 'AP-1', support_order: 1 },
          geometry: { type: 'Point', coordinates: [-5.8, 43.3] }
        }
      ]
    };
    const vanos = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { id: 'V-1', from_ap: 'AP-1', to_ap: 'AP-2' },
          geometry: { type: 'LineString', coordinates: [[-5.8, 43.3], [-5.82, 43.32]] }
        }
      ]
    };
    const worst = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { span_label: 'AP-1 -> AP-2', vperp_min: 1.2 },
          geometry: { type: 'Point', coordinates: [-5.81, 43.31] }
        }
      ]
    };

    vi.spyOn(gisLayers, 'fetchLayerData').mockImplementation((layerName: string) => {
      if (layerName === 'apoyos') {
        return Promise.resolve(apoyos);
      }
      if (layerName === 'vanos') {
        return Promise.resolve(vanos);
      }
      if (layerName === 'worst') {
        return Promise.resolve(worst);
      }
      return Promise.reject(new Error(`Unexpected layer ${layerName}`));
    });

    await gisLayers.loadCriticalSpansComposite('C:/case', layers, () => {});

    expect(layers.vanosLayer?.getSource()?.getFeatures()).toHaveLength(0);
    expect(layers.displayLayer?.getSource()?.getFeatures()).toHaveLength(0);
    expect(layers.criticalVanosAuxLayer?.getSource()?.getFeatures()).toHaveLength(1);
    expect(layers.criticalSupportsAuxLayer?.getSource()?.getFeatures()).toHaveLength(1);
    expect(layers.criticalSpansLayer?.getSource()?.getFeatures()).toHaveLength(1);
  });

  it('should still render critical spans when auxiliary layers fail', async () => {
    const layers = createLayerSet();

    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(gisLayers, 'fetchLayerData').mockImplementation((layerName: string) => {
      if (layerName === 'worst') {
        return Promise.resolve({
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              properties: { span_label: 'AP-1 -> AP-2', vperp_min: 1.2 },
              geometry: { type: 'Point', coordinates: [-5.81, 43.31] }
            }
          ]
        });
      }
      return Promise.reject(new Error(`Missing ${layerName}`));
    });

    await gisLayers.loadCriticalSpansComposite('C:/case', layers, () => {});

    expect(layers.criticalVanosAuxLayer?.getSource()?.getFeatures()).toHaveLength(0);
    expect(layers.criticalSupportsAuxLayer?.getSource()?.getFeatures()).toHaveLength(0);
    expect(layers.criticalSpansLayer?.getSource()?.getFeatures()).toHaveLength(1);
  });

  it('should clear critical composite layers when changing layer', () => {
    const layers = createLayerSet();

    layers.criticalVanosAuxLayer?.getSource()?.addFeature(new Feature({ geometry: new Point([0, 0]) }));
    layers.criticalSupportsAuxLayer?.getSource()?.addFeature(new Feature({ geometry: new Point([0, 0]) }));
    layers.criticalSpansLayer?.getSource()?.addFeature(new Feature({ geometry: new Point([0, 0]) }));

    gisLayers.clearCriticalCompositeLayers(layers);

    expect(layers.criticalVanosAuxLayer?.getSource()?.getFeatures()).toHaveLength(0);
    expect(layers.criticalSupportsAuxLayer?.getSource()?.getFeatures()).toHaveLength(0);
    expect(layers.criticalSpansLayer?.getSource()?.getFeatures()).toHaveLength(0);
  });

  it('should activate and deactivate support drawing', () => {
    (globalThis as any).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };

    component.drawMode = 'support';
    component.ngAfterViewInit();

    expect(component.drawInteraction).toBeTruthy();

    component.drawMode = 'none';
    component.ngOnChanges({
      drawMode: new SimpleChange('support', 'none', false)
    });

    expect(component.drawInteraction).toBeNull();
  });
});

function createLayerSet(): MapLayerSet {
  return {
    vanosLayer: new VectorLayer({ source: new VectorSource() }),
    displayLayer: new VectorLayer({ source: new VectorSource() }),
    criticalVanosAuxLayer: new VectorLayer({ source: new VectorSource() }),
    criticalSupportsAuxLayer: new VectorLayer({ source: new VectorSource() }),
    criticalSpansLayer: new VectorLayer({ source: new VectorSource() })
  };
}
