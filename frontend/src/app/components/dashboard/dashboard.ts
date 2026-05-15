import { Component, NgZone, OnDestroy, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { Chart, registerables } from 'chart.js';

import { DashboardAsyncStatusResponse, DashboardService, MeteoRequestPayload } from '../../services/dashboard.service';
import { MapContextService } from '../../services/map-context.service';

Chart.register(...registerables);

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

type DashboardJobStatus =
  | 'queued'
  | 'running'
  | 'finished'
  | 'successful'
  | 'completed'
  | 'success'
  | 'failed'
  | 'error';

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
  progressMessage = '';
  jobStatus: DashboardJobStatus = 'queued';
  result: DashboardAsyncStatusResponse['result'] = null;

  canGenerateDomain = false;
  isGeneratingDomain = false;
  domainGenerationMessage: string | null = null;

  private activeJobId: string | null = null;
  private pollingSubscription: Subscription | null = null;
  private monthlyChart: Chart | null = null;
  private windRoseChart: Chart | null = null;

  meteoSummary: MeteoSummary | null = null;
  windTimeseries: WindTimeseries[] = [];
  windRoseData: WindRoseData[] = [];

  chartContainerId = 'monthly-wind-chart';
  roseContainerId = 'wind-rose-chart';
  private destroy$ = new Subject<void>();

  private readonly baseCasesPath = 'C:\\Datos_TFG';

  constructor(
    private dashboardService: DashboardService,
    private mapContextService: MapContextService,
    private zone: NgZone,
    private cdr: ChangeDetectorRef
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
    this.monthlyChart?.destroy();
    this.windRoseChart?.destroy();
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
      this.canGenerateDomain = false;
      this.domainGenerationMessage = null;
    } catch (err) {
      console.error('Selección de carpeta cancelada o no soportada:', err);
    }
  }

  onAnalysisButtonClick(): void {
    if (!this.selectedYear) {
      this.error = 'Por favor selecciona un año';
      return;
    }

    this.monthlyChart?.destroy();
    this.windRoseChart?.destroy();
    this.monthlyChart = null;
    this.windRoseChart = null;

    this.isLoading = true;
    this.error = null;
    this.canGenerateDomain = false;
    this.domainGenerationMessage = null;

    this.meteoSummary = null;
    this.windTimeseries = [];
    this.windRoseData = [];

    this.validateCasePathForAnalysis((validatedPath) => {
      if (!validatedPath) {
        this.isLoading = false;
        this.cdr.detectChanges();
        return;
      }

      const requestPayload: MeteoRequestPayload = {
        year: Number(this.selectedYear),
        case_path: validatedPath,
        source: 'ERA5'
      };

      this.progress = 5;
      this.progressMessage = 'Preparando análisis...';
      this.jobStatus = 'queued';
      this.result = null;

      this.dashboardService.startMeteoSummary(requestPayload).subscribe({
        next: (response) => {
          this.activeJobId = response.job_id;
          this.startPollingJobStatus(response.job_id);
        },
        error: (err) => {
          const detail = err?.error?.detail ?? err?.message ?? 'Error desconocido';
          this.error = `Error al iniciar análisis: ${detail}`;
          this.canGenerateDomain = this.isDomainMissingError(detail);
          this.isLoading = false;
          this.cdr.detectChanges();
        }
      });
    });
  }

  private validateCasePathForAnalysis(onSuccess: (validatedCasePath: string | null) => void): void {
  const selectedPath = this.casePath.trim();

  if (!selectedPath) {
    this.error = 'Debes seleccionar una carpeta desde el botón "Seleccionar carpeta".';
    this.canGenerateDomain = false;
    this.isLoading = false;
    this.cdr.detectChanges();
    return;
  }

  this.dashboardService.getCaseStatus(selectedPath).subscribe({
    next: (status) => {
      console.log('CASE STATUS RESPONSE:', status);

      const hasDomain =
        status?.has_domain === true ||
        String((status as any)?.has_domain).toLowerCase() === 'true';

      if (!hasDomain) {
        this.error = 'El caso seleccionado no tiene dominio. Puedes generarlo automáticamente desde apoyos.';
        this.canGenerateDomain = true;
        this.domainGenerationMessage = null;
        this.isLoading = false;
        this.cdr.detectChanges();
        return;
      }

      this.canGenerateDomain = false;
      this.error = null;
      this.domainGenerationMessage = null;
      this.isLoading = true;
      this.cdr.detectChanges();

      onSuccess(selectedPath);
    },
    error: (err) => {
      const detail = err?.error?.detail ?? err?.message ?? 'No se pudo validar el caso.';

      this.error = `No se pudo validar el case_path seleccionado: ${detail}`;
      this.canGenerateDomain = true;
      this.domainGenerationMessage = null;
      this.isLoading = false;
      this.cdr.detectChanges();
    }
  });
}

  generateDomainFromDashboard(): void {
    const selectedPath = this.casePath.trim();

    if (!selectedPath) {
      this.error = 'Debes seleccionar una carpeta/caso antes de generar el dominio.';
      return;
    }

    this.isGeneratingDomain = true;
    this.canGenerateDomain = false;
    this.error = null;
    this.domainGenerationMessage = 'Generando dominio desde apoyos...';

    this.dashboardService.generateDomainFromSupports(selectedPath).subscribe({
      next: () => {
        this.isGeneratingDomain = false;
        this.canGenerateDomain = false;
        this.error = null;
        this.domainGenerationMessage = 'Dominio generado correctamente. Ya puedes lanzar el análisis meteorológico.';
        this.mapContextService.setCasePath(selectedPath);
        this.cdr.detectChanges();
      },
      error: (err) => {
        const detail = err?.error?.detail ?? err?.message ?? 'No se pudo generar el dominio.';
        this.isGeneratingDomain = false;
        this.canGenerateDomain = true;
        this.domainGenerationMessage = null;
        this.error = `No se pudo generar el dominio desde apoyos: ${detail}`;
        this.cdr.detectChanges();
      }
    });
  }

  private isDomainMissingError(message: string): boolean {
    const text = String(message ?? '').toLowerCase();

    return (
      text.includes('no existe dominio') ||
      text.includes('no tiene dominio') ||
      text.includes('falta dominio') ||
      text.includes('invalid_case_domain') ||
      text.includes('dominio.geojson') ||
      text.includes('dominio.shp') ||
      text.includes('genera el dominio')
    );
  }

  private startPollingJobStatus(jobId: string): void {
    this.stopPolling();
    this.fetchJobStatus(jobId);

    this.pollingSubscription = interval(2500)
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        if (!this.activeJobId) return;
        this.fetchJobStatus(jobId);
      });
  }

  private fetchJobStatus(jobId: string): void {
    this.dashboardService.getMeteoSummaryStatus(jobId).subscribe({
      next: (response) => {
        this.handleJobStatus(response);
      },
      error: (err) => {
        this.zone.run(() => {
          const detail = err?.error?.detail ?? 'No se pudo consultar el estado del análisis.';
          this.error = detail;
          this.canGenerateDomain = this.isDomainMissingError(detail);
          this.isLoading = false;
          this.activeJobId = null;
          this.stopPolling();
          this.cdr.detectChanges();
        });
      }
    });
  }

  private stopPolling(): void {
    this.pollingSubscription?.unsubscribe();
    this.pollingSubscription = null;
  }

  private normalizeStatus(status: string): DashboardJobStatus {
    const normalized = String(status ?? '').toLowerCase();

    if (normalized === 'successful') return 'successful';
    if (normalized === 'completed') return 'completed';
    if (normalized === 'success') return 'success';
    if (normalized === 'finished') return 'finished';
    if (normalized === 'failed') return 'failed';
    if (normalized === 'error') return 'error';
    if (normalized === 'running') return 'running';

    return 'queued';
  }

  private isFinishedStatus(status: DashboardJobStatus): boolean {
    return ['finished', 'successful', 'completed', 'success'].includes(status);
  }

  private isFailedStatus(status: DashboardJobStatus): boolean {
    return ['failed', 'error'].includes(status);
  }

  private handleJobStatus(response: DashboardAsyncStatusResponse): void {
    this.zone.run(() => {
      const status = this.normalizeStatus(response.status);

      this.jobStatus = status;
      this.progress = Math.max(0, Math.min(100, Number(response.progress ?? 0)));
      this.progressMessage = response.message ?? '';
      this.result = response.result ?? null;
      this.error = response.error ?? null;

      if (this.error) {
        this.canGenerateDomain = this.isDomainMissingError(this.error);
      }

      if (this.isFinishedStatus(status)) {
        this.progress = 100;
        this.activeJobId = null;
        this.stopPolling();

        if (response.result) {
          this.meteoSummary = response.result.meteo_summary;
          this.windTimeseries = response.result.wind_timeseries ?? [];
          this.windRoseData = response.result.wind_rose ?? [];
        }

        this.isLoading = false;
        this.canGenerateDomain = false;
        this.cdr.detectChanges();
        this.renderCharts();
      }

      if (this.isFailedStatus(status)) {
        this.activeJobId = null;
        this.stopPolling();

        const detail = response.error || 'El análisis no pudo completarse.';
        this.error = detail;
        this.canGenerateDomain = this.isDomainMissingError(detail);
        this.isLoading = false;
      }

      this.cdr.detectChanges();
    });
  }

  private renderCharts(): void {
    setTimeout(() => {
      this.renderMonthlyChart();
      this.renderWindRoseChart();
    }, 100);
  }

  private renderMonthlyChart(): void {
    const canvas = document.getElementById(this.chartContainerId) as HTMLCanvasElement | null;
    if (!canvas) return;

    this.monthlyChart?.destroy();

    const labels = this.windTimeseries.map(data =>
      new Intl.DateTimeFormat('es-ES', { month: 'long' }).format(new Date(2024, data.month - 1))
    );

    const avgData = this.windTimeseries.map(data => data.avg_velocity);
    const maxData = this.windTimeseries.map(data => data.max_velocity);

    this.monthlyChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Velocidad media (m/s)',
            data: avgData
          },
          {
            label: 'Velocidad máxima (m/s)',
            data: maxData,
            type: 'line',
            tension: 0.3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top'
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            title: {
              display: true,
              text: 'm/s'
            }
          }
        }
      }
    });
  }

  private renderWindRoseChart(): void {
    const canvas = document.getElementById(this.roseContainerId) as HTMLCanvasElement | null;
    if (!canvas) return;

    this.windRoseChart?.destroy();

    const labels = this.windRoseData.map(data => data.direction);
    const values = this.windRoseData.map(data => Number((data.frequency * 100).toFixed(2)));

    this.windRoseChart = new Chart(canvas, {
      type: 'polarArea',
      data: {
        labels,
        datasets: [
          {
            label: 'Frecuencia (%)',
            data: values
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'right'
          },
          tooltip: {
            callbacks: {
              label: (context) => `${context.label}: ${context.parsed} %`
            }
          }
        }
      }
    });
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