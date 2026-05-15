import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface MeteoSummary {
  year: number;
  avg_velocity: number;
  max_velocity: number;
  dominant_direction: number;
  windiest_month: number;
  viability_index: number;
  data_points: number;
}

export interface WindTimeseries {
  month: number;
  avg_velocity: number;
  max_velocity: number;
  min_velocity: number;
  frequency: Record<string, number>;
}

export interface WindRoseData {
  direction: string;
  frequency: number;
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

export interface DashboardAsyncStatusResponse {
  job_id: string;
  status:
    | 'queued'
    | 'running'
    | 'finished'
    | 'successful'
    | 'completed'
    | 'success'
    | 'failed'
    | 'error';
  progress: number;
  message: string;
  result: {
    meteo_summary: MeteoSummary;
    wind_timeseries: WindTimeseries[];
    wind_rose: WindRoseData[];
  } | null;
  error: string | null;
}

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

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly apiBaseUrl = environment.apiBaseUrl;
  constructor(private http: HttpClient) {}

  startMeteoSummary(payload: MeteoRequestPayload): Observable<DashboardAsyncStartResponse> {
    return this.http.post<DashboardAsyncStartResponse>(`${this.apiBaseUrl}/dashboard/meteo-summary/start`, payload);
  }
  getMeteoSummaryStatus(jobId: string): Observable<DashboardAsyncStatusResponse> {
    return this.http.get<DashboardAsyncStatusResponse>(`${this.apiBaseUrl}/dashboard/meteo-summary/status/${jobId}`);
  }
  getMeteoSummary(payload: MeteoRequestPayload): Observable<MeteoSummary> {
    return this.http.post<MeteoSummary>(`${this.apiBaseUrl}/dashboard/meteo-summary`, payload);
  }
  getWindTimeseries(payload: MeteoRequestPayload): Observable<WindTimeseries[]> {
    return this.http.post<WindTimeseries[]>(`${this.apiBaseUrl}/dashboard/wind-timeseries`, payload);
  }
  getWindRose(payload: MeteoRequestPayload): Observable<WindRoseData[]> {
    return this.http.post<WindRoseData[]>(`${this.apiBaseUrl}/dashboard/wind-rose`, payload);
  }
  getCaseStatus(casePath: string): Observable<CaseStatusResponse> {
    return this.http.post<CaseStatusResponse>(`${this.apiBaseUrl}/case/status`, { case_path: casePath });
  }
  generateDomainFromSupports(casePath: string): Observable<GenerateDomainFromSupportsResponse> {
    return this.http.post<GenerateDomainFromSupportsResponse>(
      `${this.apiBaseUrl}/domain/generate-from-supports`,
      { case_path: casePath }
    );
  }
}
