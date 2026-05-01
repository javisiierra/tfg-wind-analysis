import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { DashboardService, MeteoRequestPayload } from '../../services/dashboard.service';
import { MapContextService } from '../../services/map-context.service';

interface MeteoSummary {
  year: number;
  avg_velocity: number;
  max_velocity: number;
  dominant_direction: number;
  windiest_month: number;
  viability_index: number;
  data_points: number;
}

interface WindTimeseries {
  month: number;
  avg_velocity: number;
  max_velocity: number;
  min_velocity: number;
  frequency: Record<string, number>;
}

interface WindRoseData {
  direction: string;
  frequency: number;
  velocity_range: { min: number; max: number };
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css'
})
export class DashboardComponent implements OnInit, OnDestroy {
  years: number[] = [];
  selectedYear: number | null = null;
  selectedDomainType: 'domain_id' | 'bbox' | 'case_path' = 'domain_id';
  domainId = '';
  bboxText = '';
  casePath = '';
  manualCasePath = '';
  useManualCasePath = false;
  isLoading = false;
  error: string | null = null;

  meteoSummary: MeteoSummary | null = null;
  windTimeseries: WindTimeseries[] = [];
  windRoseData: WindRoseData[] = [];

  chartContainerId = 'monthly-wind-chart';
  roseContainerId = 'wind-rose-chart';
  private destroy$ = new Subject<void>();

  constructor(
    private dashboardService: DashboardService,
    private mapContextService: MapContextService
  ) {
    this.initializeYears();
  }

  ngOnInit(): void {
    this.mapContextService.casePath$
      .pipe(takeUntil(this.destroy$))
      .subscribe(path => {
        this.casePath = path ?? '';
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private initializeYears(): void {
    const currentYear = new Date().getFullYear();
    this.years = [];
    for (let i = currentYear; i >= currentYear - 10; i--) {
      this.years.push(i);
    }
    if (this.years.length > 0) {
      this.selectedYear = this.years[0];
    }
  }

  onAnalysisButtonClick(): void {
    if (!this.selectedYear) {
      this.error = 'Por favor selecciona un año';
      return;
    }
    this.isLoading = true;
    this.error = null;

    this.validateCasePathForAnalysis((validatedPath) => {
      const domainRequest = this.buildDomainRequest(validatedPath);
      if (!domainRequest) {
        this.isLoading = false;
        return;
      }

      this.dashboardService.getMeteoSummary(domainRequest).subscribe({
        next: (summary) => {
          this.meteoSummary = summary;
          this.loadWindTimeseries(domainRequest);
        },
        error: (err) => {
          this.error = `Error al obtener resumen meteorológico: ${err.message}`;
          this.isLoading = false;
        }
      });
    });
  }

  get selectedCasePathForRequest(): string {
    return this.useManualCasePath ? this.manualCasePath.trim() : this.casePath.trim();
  }

  private validateCasePathForAnalysis(onSuccess: (validatedCasePath: string | null) => void): void {
    if (this.selectedDomainType !== 'case_path') {
      onSuccess(null);
      return;
    }

    const selectedPath = this.selectedCasePathForRequest;
    if (!selectedPath) {
      this.error = 'Debes seleccionar un caso activo o pegar un case_path manual.';
      this.isLoading = false;
      return;
    }

    this.dashboardService.getCaseStatus(selectedPath).subscribe({
      next: (status) => {
        if (!status.has_domain) {
          this.error = 'El caso seleccionado no tiene dominio.*. Genera el dominio antes de lanzar el análisis.';
          this.isLoading = false;
          return;
        }
        onSuccess(selectedPath);
      },
      error: (err) => {
        const detail = err?.error?.detail ?? err?.message ?? 'No se pudo validar el caso.';
        this.error = `No se pudo validar el case_path seleccionado: ${detail}`;
        this.isLoading = false;
      }
    });
  }

  private loadWindTimeseries(payload: MeteoRequestPayload): void {
    this.dashboardService.getWindTimeseries(payload).subscribe({
      next: (data) => {
        this.windTimeseries = data;
        this.loadWindRose(payload);
      },
      error: (err) => {
        this.error = `Error al obtener series temporales: ${err.message}`;
        this.isLoading = false;
      }
    });
  }

  private loadWindRose(payload: MeteoRequestPayload): void {
    this.dashboardService.getWindRose(payload).subscribe({
      next: (data) => {
        this.windRoseData = data;
        this.renderCharts();
        this.isLoading = false;
      },
      error: (err) => {
        this.error = `Error al obtener rosa de vientos: ${err.message}`;
        this.isLoading = false;
      }
    });
  }

  private renderCharts(): void {
    setTimeout(() => {
      this.renderMonthlyChart();
      this.renderWindRoseChart();
    }, 100);
  }

  private renderMonthlyChart(): void {
    const container = document.getElementById(this.chartContainerId);
    if (!container) return;

    // Simple chart rendering - can be replaced with Chart.js or similar
    let html = '<div class="chart-placeholder"><p>Gráfico de viento mensual</p>';
    if (this.windTimeseries.length > 0) {
      html += '<table class="data-table"><tr><th>Mes</th><th>Vel. Media</th><th>Vel. Máx</th></tr>';
      this.windTimeseries.forEach(data => {
        const monthName = new Intl.DateTimeFormat('es-ES', { month: 'long' })
          .format(new Date(2024, data.month - 1));
        html += `<tr><td>${monthName}</td><td>${data.avg_velocity.toFixed(2)} m/s</td><td>${data.max_velocity.toFixed(2)} m/s</td></tr>`;
      });
      html += '</table>';
    }
    html += '</div>';
    container.innerHTML = html;
  }

  private renderWindRoseChart(): void {
    const container = document.getElementById(this.roseContainerId);
    if (!container) return;

    // Simple rose chart rendering - can be replaced with proper visualization library
    let html = '<div class="chart-placeholder"><p>Rosa de vientos</p>';
    if (this.windRoseData.length > 0) {
      html += '<ul class="wind-rose-list">';
      this.windRoseData.forEach(data => {
        html += `<li><strong>${data.direction}</strong>: ${(data.frequency * 100).toFixed(1)}%</li>`;
      });
      html += '</ul>';
    }
    html += '</div>';
    container.innerHTML = html;
  }

  getDirectionLabel(degrees: number): string {
    const directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
    const index = Math.round(degrees / 22.5) % 16;
    return directions[index];
  }

  getViabilityStatus(index: number): string {
    if (index >= 0.7) return 'Muy Alta';
    if (index >= 0.5) return 'Alta';
    if (index >= 0.3) return 'Media';
    return 'Baja';
  }

  getViabilityClass(index: number): string {
    if (index >= 0.7) return 'viability-high';
    if (index >= 0.5) return 'viability-medium-high';
    if (index >= 0.3) return 'viability-medium';
    return 'viability-low';
  }

  private buildDomainRequest(validatedCasePath: string | null): MeteoRequestPayload | null {
    if (!this.selectedYear) {
      return null;
    }
    const baseRequest: MeteoRequestPayload = { year: this.selectedYear };
    if (this.selectedDomainType === 'domain_id') {
      if (!this.domainId.trim()) {
        this.error = 'Debes informar un domain_id';
        return null;
      }
      return { ...baseRequest, domain_id: this.domainId.trim() };
    }

    if (this.selectedDomainType === 'case_path') {
      if (!validatedCasePath) {
        this.error = 'Debes informar un case_path válido';
        return null;
      }
      return { ...baseRequest, case_path: validatedCasePath };
    }

    const values = this.bboxText.split(',').map((value) => Number(value.trim()));
    if (values.length !== 4 || values.some((value) => Number.isNaN(value))) {
      this.error = 'El bbox debe tener 4 números separados por coma: minLon,minLat,maxLon,maxLat';
      return null;
    }
    const [minLon, minLat, maxLon, maxLat] = values;
    if (minLon >= maxLon || minLat >= maxLat) {
      this.error = 'El bbox es inválido: min debe ser menor que max';
      return null;
    }
    return { ...baseRequest, bbox: [minLon, minLat, maxLon, maxLat] };
  }
}
