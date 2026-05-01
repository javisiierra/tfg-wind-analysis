import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { DashboardAsyncStatusResponse, DashboardService, MeteoRequestPayload } from '../../services/dashboard.service';
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
  casePath = '';
  isLoading = false;
  error: string | null = null;
  progress = 0;
  progressMessage = "";
  jobStatus: 'queued' | 'running' | 'finished' | 'failed' = 'queued';
  result: DashboardAsyncStatusResponse['result'] = null;
  private activeJobId: string | null = null;
  private pollingSubscription: Subscription | null = null;

  meteoSummary: MeteoSummary | null = null;
  windTimeseries: WindTimeseries[] = [];
  windRoseData: WindRoseData[] = [];

  chartContainerId = 'monthly-wind-chart';
  roseContainerId = 'wind-rose-chart';
  private destroy$ = new Subject<void>();

  private readonly baseCasesPath = 'C:\\Datos_TFG';

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
    this.stopPolling();
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


  async selectFolderFromDashboard(): Promise<void> {
    try {
      const dirHandle = await (window as any).showDirectoryPicker();
      const selectedPath = `${this.baseCasesPath}\\${dirHandle.name}`;
      this.casePath = selectedPath;
      this.mapContextService.setCasePath(selectedPath);
      this.error = null;
    } catch (err) {
      console.error('Selección de carpeta cancelada o no soportada:', err);
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
      if (!validatedPath) {
        this.error = 'Debes seleccionar una carpeta/caso válido.';
        this.isLoading = false;
        return;
      }

      const requestPayload: MeteoRequestPayload = { year: this.selectedYear!, case_path: validatedPath, source: "ERA5" };
      this.progress = 5;
      this.progressMessage = "Preparando análisis...";
      this.jobStatus = "queued";
      this.result = null;
      this.dashboardService.startMeteoSummary(requestPayload).subscribe({
        next: (response) => {
          this.activeJobId = response.job_id;
          this.startPollingJobStatus(response.job_id);
        },
        error: (err) => {
          this.error = `Error al iniciar análisis: ${err.message}`;
          this.isLoading = false;
        }
      });
    });
  }

  private validateCasePathForAnalysis(onSuccess: (validatedCasePath: string | null) => void): void {
    const selectedPath = this.casePath.trim();
    if (!selectedPath) {
      this.error = 'Debes seleccionar una carpeta desde el botón "Seleccionar carpeta" de la barra superior.';
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

  private startPollingJobStatus(jobId: string): void {
    this.stopPolling();
    this.pollingSubscription = interval(2500).pipe(takeUntil(this.destroy$)).subscribe(() => {
      if (!this.activeJobId) return;
      this.dashboardService.getMeteoSummaryStatus(jobId).subscribe({
        next: (response) => this.handleJobStatus(response),
        error: () => {
          this.error = "No se pudo consultar el estado del análisis.";
          this.isLoading = false;
          this.activeJobId = null;
          this.stopPolling();
        }
      });
    });
    this.dashboardService.getMeteoSummaryStatus(jobId).subscribe((status) => this.handleJobStatus(status));
  }

  private stopPolling(): void {
    this.pollingSubscription?.unsubscribe();
    this.pollingSubscription = null;
  }

  private handleJobStatus(response: DashboardAsyncStatusResponse): void {
    console.log('JOB STATUS RESPONSE', response);
    this.jobStatus = response.status;
    this.progress = response.progress ?? 0;
    this.progressMessage = response.message ?? '';
    this.result = response.result ?? null;
    this.error = response.error ?? null;

    if (response.status === "finished") {
      this.activeJobId = null;
      this.stopPolling();
      if (response.result) {
        this.meteoSummary = response.result.meteo_summary;
        this.windTimeseries = response.result.wind_timeseries;
        this.windRoseData = response.result.wind_rose;
      }
      this.renderCharts();
      this.isLoading = false;
    }
    if (response.status === "failed") {
      this.activeJobId = null;
      this.stopPolling();
      this.error = response.error || "El análisis no pudo completarse.";
      this.isLoading = false;
    }
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
}
