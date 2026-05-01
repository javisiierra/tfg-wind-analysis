import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

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

@Injectable({
  providedIn: 'root'
})
export class DashboardService {
  private apiUrl = 'http://localhost:8000/api/v1';

  constructor(private http: HttpClient) {}

  /**
   * Obtiene el resumen meteorológico para un año específico
   * @param year Año para el cual obtener el resumen
   * @returns Observable con los datos del resumen meteorológico
   */
  getMeteoSummary(year: number): Observable<MeteoSummary> {
    return this.http.post<MeteoSummary>(
      `${this.apiUrl}/dashboard/meteo-summary`,
      { year }
    );
  }

  /**
   * Obtiene las series temporales de viento por mes
   * @param year Año para el cual obtener los datos
   * @returns Observable con las series temporales de viento
   */
  getWindTimeseries(year: number): Observable<WindTimeseries[]> {
    return this.http.post<WindTimeseries[]>(
      `${this.apiUrl}/dashboard/wind-timeseries`,
      { year }
    );
  }

  /**
   * Obtiene los datos de rosa de vientos
   * @param year Año para el cual obtener los datos
   * @returns Observable con los datos de rosa de vientos
   */
  getWindRose(year: number): Observable<WindRoseData[]> {
    return this.http.post<WindRoseData[]>(
      `${this.apiUrl}/dashboard/wind-rose`,
      { year }
    );
  }
}
