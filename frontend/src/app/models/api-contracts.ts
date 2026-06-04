export type PipelineStatus = 'ok' | 'ready';
export type DashboardJobStatus = 'queued' | 'running' | 'finished' | 'failed';

export interface APIErrorDTO {
  code: string;
  message: string;
  stage?: string;
}

export interface SupportDTO {
  id: string;
  support_order: number;
  support_total?: number;
}

export interface SpanDTO {
  id: string;
  from_support: string;
  to_support: string;
  from_order?: number;
  to_order?: number;
  direction_deg: number;
}

export interface DomainDTO {
  domain_shp?: string;
  domain_geojson?: string;
  source?: string;
  buffer_m?: number;
  crs?: string;
}

export interface WorstSupportDTO {
  from_support: string;
  to_support: string;
  span_label: string;
  critical_metric: number;
  critical_metric_unit: 'm/s';
  critical_reason: string;
  direction_deg?: number;
  wind_speed?: number;
  wind_speed_unit: 'm/s';
  wind_direction?: number;
  angle_relative?: number;
  angle_relative_unit: 'deg';
}

export interface MeteoSummaryDTO {
  year: number;
  avg_velocity: number;
  max_velocity: number;
  dominant_direction: number;
  windiest_month: number;
  viability_index: number;
  data_points: number;
}

export interface WindTimeseriesDTO {
  month: number;
  avg_velocity: number;
  max_velocity: number;
  min_velocity: number;
  frequency: Record<string, number>;
}

export interface WindRoseDTO {
  direction: string;
  frequency: number;
  mean_speed?: number;
  sample_count?: number;
  velocity_range: { min: number; max: number };
}

export interface DashboardJobResultDTO {
  meteo_summary: MeteoSummaryDTO;
  wind_timeseries: WindTimeseriesDTO[];
  wind_rose: WindRoseDTO[];
}

export interface DashboardJobStatusDTO {
  job_id: string;
  status: DashboardJobStatus;
  progress: number;
  message: string;
  result: DashboardJobResultDTO | null;
  error: string | null;
}

export interface PipelineStatusDTO {
  status: PipelineStatus;
  case_path?: string;
  message?: string;
  [key: string]: unknown;
}
