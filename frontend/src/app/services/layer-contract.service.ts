type GeoJsonFeature = {
  properties?: Record<string, unknown> | null;
};

export type GeoJsonFeatureCollection = {
  type: 'FeatureCollection';
  features: GeoJsonFeature[];
  [key: string]: unknown;
};

function firstProperty(props: Record<string, unknown>, names: string[]): unknown {
  for (const name of names) {
    const value = props[name];
    if (value !== undefined && value !== null && value !== '') return value;
  }
  return undefined;
}

function supportLabel(value: unknown): string | undefined {
  if (value === undefined || value === null || value === '') return undefined;
  const text = String(value).trim();
  if (!text) return undefined;
  const numeric = Number(text);
  return Number.isFinite(numeric) ? `AP-${Math.trunc(numeric)}` : text;
}

function setNumericProperty(props: Record<string, unknown>, name: string, value: unknown): void {
  const numeric = Number(value);
  if (value !== undefined && value !== null && value !== '' && Number.isFinite(numeric)) {
    props[name] = numeric;
  }
}

function normalizeSupports(features: GeoJsonFeature[]): void {
  features.forEach((feature, index) => {
    const props = feature.properties ?? {};
    const order = Number(firstProperty(props, ['support_order', 'support_or', 'sup_order', 'SUPPORT_ORDER', 'SUP_ORDER']) ?? index + 1);
    const total = Number(firstProperty(props, ['support_total', 'support_to', 'sup_total', 'SUPPORT_TOTAL', 'SUP_TOTAL']) ?? features.length);
    props['id'] = supportLabel(firstProperty(props, ['id', 'ID', 'support_id', 'SUPPORT_ID'])) ?? `AP-${order}`;
    props['support_order'] = order;
    props['support_total'] = total;
    feature.properties = props;
  });
}

function normalizeSpans(features: GeoJsonFeature[]): void {
  features.forEach((feature, index) => {
    const props = feature.properties ?? {};
    const fromOrder = firstProperty(props, ['from_order', 'from_ord', 'from_idx']);
    const toOrder = firstProperty(props, ['to_order', 'to_ord', 'to_idx']);
    props['id'] = String(firstProperty(props, ['id', 'vano_id', 'MAT']) ?? `V-${index + 1}`);
    props['from_support'] = supportLabel(firstProperty(props, ['from_support', 'from_support_id', 'from_ap'])) ?? supportLabel(fromOrder);
    props['to_support'] = supportLabel(firstProperty(props, ['to_support', 'to_support_id', 'to_ap'])) ?? supportLabel(toOrder);
    setNumericProperty(props, 'direction_deg', firstProperty(props, ['direction_deg', 'direction', 'direccion', 'direccio']));
    setNumericProperty(props, 'from_order', fromOrder);
    setNumericProperty(props, 'to_order', toOrder);
    feature.properties = props;
  });
}

function normalizeWorstSupports(features: GeoJsonFeature[]): void {
  features.forEach((feature) => {
    const props = feature.properties ?? {};
    const fromSupport = supportLabel(firstProperty(props, ['from_support', 'from_support_id', 'from_ap']));
    const toSupport = supportLabel(firstProperty(props, ['to_support', 'to_support_id', 'to_ap']));
    props['from_support'] = fromSupport;
    props['to_support'] = toSupport;
    const spanLabel = firstProperty(props, ['span_label', 'span_labe'])
      ?? (fromSupport && toSupport ? `${fromSupport} -> ${toSupport}` : undefined);
    if (spanLabel !== undefined) props['span_label'] = spanLabel;
    setNumericProperty(props, 'critical_metric', firstProperty(props, ['critical_metric', 'vperp_min', 'v_perp']));
    setNumericProperty(props, 'direction_deg', firstProperty(props, ['direction_deg', 'direction', 'direccion', 'direccio']));
    setNumericProperty(props, 'wind_speed', firstProperty(props, ['wind_speed', 'w_speed']));
    setNumericProperty(props, 'wind_direction', firstProperty(props, ['wind_direction', 'wind_dir', 'w_dir']));
    setNumericProperty(props, 'angle_relative', firstProperty(props, ['angle_relative', 'alpha_eff', 'alpha']));
    feature.properties = props;
  });
}

export function normalizeLayerGeoJson(layerName: string, data: GeoJsonFeatureCollection): GeoJsonFeatureCollection {
  if (!data?.features) return data;
  if (layerName === 'apoyos') normalizeSupports(data.features);
  if (layerName === 'vanos') normalizeSpans(data.features);
  if (layerName === 'worst') normalizeWorstSupports(data.features);
  return data;
}
