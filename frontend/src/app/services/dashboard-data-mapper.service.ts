import { Injectable } from '@angular/core';
import {
  DashboardJobResultDTO,
  DashboardJobStatus,
  MeteoSummaryDTO,
  WindRoseDTO,
  WindTimeseriesDTO
} from '../models/api-contracts';
import { DashboardAsyncStatusResponse, MeteoRequestPayload } from './dashboard.service';

export interface DashboardResultViewModel {
  meteoSummary: MeteoSummaryDTO | null;
  windTimeseries: WindTimeseriesDTO[];
  windRoseData: WindRoseDTO[];
}

@Injectable({
  providedIn: 'root'
})
export class DashboardDataMapperService {
  createMeteoRequestPayload(year: number, casePath: string): MeteoRequestPayload {
    return {
      year: Number(year),
      case_path: casePath,
      source: 'ERA5'
    };
  }

  mapJobResult(result: DashboardJobResultDTO | null | undefined): DashboardResultViewModel {
    return {
      meteoSummary: result?.meteo_summary ?? null,
      windTimeseries: result?.wind_timeseries ?? [],
      windRoseData: result?.wind_rose ?? []
    };
  }

  clampProgress(progress: unknown): number {
    return Math.max(0, Math.min(100, Number(progress ?? 0)));
  }

  normalizeStatusResponse(response: DashboardAsyncStatusResponse): DashboardAsyncStatusResponse {
    return {
      ...response,
      progress: this.clampProgress(response.progress),
      message: response.message ?? '',
      result: response.result ?? null,
      error: response.error ?? null
    };
  }

  hasDomain(status: unknown): boolean {
    const value = (status as { has_domain?: unknown } | null)?.has_domain;
    return value === true || String(value).toLowerCase() === 'true';
  }

  errorDetail(err: any, fallback: string): string {
    return err?.error?.detail ?? err?.message ?? fallback;
  }

  isFinishedStatus(status: DashboardJobStatus): boolean {
    return status === 'finished';
  }

  isFailedStatus(status: DashboardJobStatus): boolean {
    return status === 'failed';
  }
}
