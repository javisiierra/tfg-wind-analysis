import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { map, Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  DashboardJobStatus,
  DashboardJobStatusDTO,
  MeteoSummaryDTO,
  WindRoseDTO,
  WindTimeseriesDTO
} from '../models/api-contracts';

export type MeteoSummary = MeteoSummaryDTO;
export type WindTimeseries = WindTimeseriesDTO;
export type WindRoseData = WindRoseDTO;

interface LegacyWindRoseData {
  direction: string;
  frequency?: number | Record<string, unknown>;
  percentage?: number;
  value?: number;
  freq?: number;
  mean_speed?: number;
  avg_velocity?: number;
  sample_count?: number;
  samples?: number;
  count?: number;
  velocity_range: { min: number; max: number };
}

export interface MeteoRequestPayload {
  year: number;
  domain_id?: string;
  geometry?: Record<string, unknown>;
  bbox?: [number, number, number, number];
  case_path?: string;
  source?: string;
}

export interface DashboardAsyncStartResponse { job_id: string; status: 'queued'; }

export type DashboardAsyncStatusResponse = DashboardJobStatusDTO;

export interface CaseStatusResponse {
  case_path: string;
  has_domain: boolean;
  has_weather: boolean;
  has_dem: boolean;
  has_apoyos: boolean;
  has_vanos: boolean;
  ready_for_windninja: boolean;
}

export interface GenerateDomainFromSupportsResponse {
  ok?: boolean;
  status?: string;
  message?: string;
  domain_path?: string;
  geojson_path?: string;
  [key: string]: unknown;
}

export interface GenerateVanosFromSupportsResponse {
  status: string;
  message: string;
  created: boolean;
  vanos_count: number;
  output_shp: string;
  output_geojson: string;
  [key: string]: unknown;
}

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly apiUrl = environment.apiUrl;
  constructor(private http: HttpClient) {}

  startMeteoSummary(payload: MeteoRequestPayload): Observable<DashboardAsyncStartResponse> {
    return this.http.post<DashboardAsyncStartResponse>(`${this.apiUrl}/dashboard/meteo-summary/start`, payload);
  }
  getMeteoSummaryStatus(jobId: string): Observable<DashboardAsyncStatusResponse> {
    return this.http.get<Omit<DashboardAsyncStatusResponse, 'status'> & { status: string }>(
      `${this.apiUrl}/dashboard/meteo-summary/status/${jobId}`
    ).pipe(
      map(response => ({
        ...response,
        status: this.normalizeDashboardJobStatus(response.status),
        result: response.result
          ? { ...response.result, wind_rose: response.result.wind_rose.map(item => this.normalizeWindRose(item)) }
          : null
      }))
    );
  }
  getMeteoSummary(payload: MeteoRequestPayload): Observable<MeteoSummary> {
    return this.http.post<MeteoSummary>(`${this.apiUrl}/dashboard/meteo-summary`, payload);
  }
  getWindTimeseries(payload: MeteoRequestPayload): Observable<WindTimeseries[]> {
    return this.http.post<WindTimeseries[]>(`${this.apiUrl}/dashboard/wind-timeseries`, payload);
  }
  getWindRose(payload: MeteoRequestPayload): Observable<WindRoseData[]> {
    return this.http.post<LegacyWindRoseData[]>(`${this.apiUrl}/dashboard/wind-rose`, payload)
      .pipe(map(items => items.map(item => this.normalizeWindRose(item))));
  }
  getCaseStatus(casePath: string): Observable<CaseStatusResponse> {
    return this.http.post<CaseStatusResponse>(`${this.apiUrl}/case/status`, { case_path: casePath });
  }
  generateDomainFromSupports(casePath: string): Observable<GenerateDomainFromSupportsResponse> {
    return this.http.post<GenerateDomainFromSupportsResponse>(
      `${this.apiUrl}/domain/generate-from-supports`,
      { case_path: casePath }
    );
  }
  generateVanosFromSupports(casePath: string): Observable<GenerateVanosFromSupportsResponse> {
    return this.http.post<GenerateVanosFromSupportsResponse>(
      `${this.apiUrl}/vanos/generate-from-supports`,
      { case_path: casePath }
    );
  }

  private normalizeDashboardJobStatus(status: string): DashboardJobStatus {
    const normalized = String(status ?? '').toLowerCase();
    if (['finished', 'successful', 'completed', 'success'].includes(normalized)) return 'finished';
    if (['failed', 'error'].includes(normalized)) return 'failed';
    return normalized === 'running' ? 'running' : 'queued';
  }

  private normalizeWindRose(item: LegacyWindRoseData): WindRoseDTO {
    return {
      direction: item.direction,
      frequency: this.numericValue(item.frequency ?? item.percentage ?? item.value ?? item.freq) ?? 0,
      mean_speed: this.numericValue(item.mean_speed ?? item.avg_velocity),
      sample_count: this.numericValue(item.sample_count ?? item.samples ?? item.count),
      velocity_range: item.velocity_range
    };
  }

  private numericValue(value: unknown): number | undefined {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : undefined;
  }
}
