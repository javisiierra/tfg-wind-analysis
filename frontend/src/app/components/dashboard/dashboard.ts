import { Component, NgZone, OnDestroy, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, Subscription, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { Chart, ChartConfiguration, ChartOptions, registerables } from 'chart.js';

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
  frequency?: number | Record<string, unknown>;
  percentage?: number;
  value?: number;
  freq?: number;
  mean_speed?: number;
  avg_velocity?: number;
  sample_count?: number;
  samples?: number;
  count?: number;
  velocity_range?: { min?: number; max?: number };
}

interface WindRoseSector {
  direction: string;
  percentage: number | null;
  meanSpeed: number | null;
  samples: number | null;
  velocity_range?: { min?: number; max?: number };
  raw: WindRoseData | null;
  angle: number;
  path: string;
  color: string;
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
  etaMessage = '';
  jobStatus: DashboardJobStatus = 'queued';
  result: DashboardAsyncStatusResponse['result'] = null;

  canGenerateDomain = false;
  isGeneratingDomain = false;
  domainGenerationMessage: string | null = null;

  private activeJobId: string | null = null;
  private analysisStartedAtMs: number | null = null;
  private pollingSubscription: Subscription | null = null;
  private monthlyChart: Chart | null = null;

  meteoSummary: MeteoSummary | null = null;
  windTimeseries: WindTimeseries[] = [];
  windRoseData: WindRoseData[] = [];
  windRoseSectors: WindRoseSector[] = [];
  selectedWindSector: WindRoseSector | null = null;

  chartContainerId = 'monthly-wind-chart';
  private destroy$ = new Subject<void>();

  private readonly baseCasesPath = '/data';
  readonly windRoseDirections = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  readonly windRoseRings = [3, 6, 9, 12];
  private readonly windRoseCenter = 210;
  private readonly windRoseMaxRadius = 150;
  private readonly windRoseInnerRadius = 4;
  private readonly windRoseSectorDegrees = 360 / this.windRoseDirections.length;
  private readonly windRosePalette = [
    '#0ea5e9', '#be4372', '#a76732', '#d6bd67',
    '#2e938c', '#6d49bd', '#8c929d', '#126898',
    '#be4372', '#a76732', '#a69355', '#31949a',
    '#6d49bd', '#8c929d', '#126898', '#be4372'
  ];
  private readonly monthlyWindChartOptions: ChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'nearest',
      intersect: false
    },
    hover: {
      mode: 'nearest',
      intersect: false
    },
    plugins: {
      legend: {
        position: 'top'
      },
      tooltip: {
        enabled: true,
        mode: 'nearest',
        intersect: false,
        callbacks: {
          title: (items) => items[0]?.label ?? '',
          label: (context) => {
            const label = context.dataset.label ?? '';
            const value = typeof context.parsed.y === 'number'
              ? context.parsed.y.toFixed(2)
              : context.formattedValue;

            return `${label}: ${value} m/s`;
          }
        }
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
  };

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
      const selectedPath = `${this.baseCasesPath}/${dirHandle.name}`;

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
    this.monthlyChart = null;

    this.isLoading = true;
    this.error = null;
    this.etaMessage = '';
    this.analysisStartedAtMs = null;
    this.canGenerateDomain = false;
    this.domainGenerationMessage = null;

    this.meteoSummary = null;
    this.windTimeseries = [];
    this.windRoseData = [];
    this.windRoseSectors = [];
    this.selectedWindSector = null;

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
      this.etaMessage = 'Calculando tiempo estimado...';
      this.analysisStartedAtMs = Date.now();
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
          this.etaMessage = '';
          this.analysisStartedAtMs = null;
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
          this.etaMessage = '';
          this.analysisStartedAtMs = null;
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
      this.etaMessage = this.buildEtaMessage(this.progress, status, this.progressMessage);
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
          this.windRoseSectors = this.buildWindRoseSectors(this.windRoseData);
          this.selectedWindSector = null;
        }

        this.isLoading = false;
        this.etaMessage = '';
        this.analysisStartedAtMs = null;
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
        this.etaMessage = '';
        this.analysisStartedAtMs = null;
      }

      this.cdr.detectChanges();
    });
  }

  private buildEtaMessage(progress: number, status: DashboardJobStatus, progressMessage: string): string {
    if (!this.analysisStartedAtMs || this.isFinishedStatus(status)) {
      return '';
    }

    const elapsedMs = Date.now() - this.analysisStartedAtMs;

    if (progress <= 0 || elapsedMs < 1000) {
      return 'Backend activo. Calculando tiempo estimado...';
    }

    const elapsedText = this.formatDuration(elapsedMs);
    const normalizedProgress = Math.max(5, Math.min(progress, 95));
    const progressBasedRemainingMs = elapsedMs * ((100 - normalizedProgress) / normalizedProgress);
    const message = String(progressMessage ?? '').toLowerCase();

    if (progress >= 75 && progress < 90) {
      return `Backend activo. Tiempo transcurrido: ${elapsedText}. Esperando a Copernicus/ERA5; esta fase puede tardar 5-10 min.`;
    }

    if (progress >= 90) {
      return `Backend activo. Tiempo transcurrido: ${elapsedText}. Ultimos calculos, queda poco.`;
    }

    const nominalTotalMs = message.includes('cache') ? 120000 : 600000;
    const nominalRemainingMs = Math.max(0, nominalTotalMs - elapsedMs);
    const remainingMs = Math.max(progressBasedRemainingMs, nominalRemainingMs);

    return `Backend activo. Transcurrido: ${elapsedText}. Estimado restante: ${this.formatDuration(remainingMs)} aprox.`;
  }

  private formatDuration(durationMs: number): string {
    const totalSeconds = Math.max(1, Math.round(durationMs / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    if (minutes <= 0) {
      return `${seconds} s`;
    }

    if (seconds === 0) {
      return `${minutes} min`;
    }

    return `${minutes} min ${seconds} s`;
  }

  private renderCharts(): void {
    setTimeout(() => {
      this.renderMonthlyChart();
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

    const monthlyWindChartConfig: ChartConfiguration = {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Velocidad media (m/s)',
            data: avgData,
            backgroundColor: 'rgba(37, 99, 235, .72)',
            borderColor: '#60a5fa',
            borderWidth: 1,
            hoverBackgroundColor: 'rgba(37, 99, 235, .92)'
          },
          {
            label: 'Velocidad máxima (m/s)',
            data: maxData,
            type: 'line',
            tension: 0.3,
            borderColor: '#ef4444',
            backgroundColor: '#ef4444',
            pointBackgroundColor: '#ef4444',
            pointBorderColor: '#fecaca',
            pointRadius: 4,
            pointHoverRadius: 6
          }
        ]
      },
      options: this.monthlyWindChartOptions
    };

    this.monthlyChart = new Chart(canvas, monthlyWindChartConfig);
  }

  selectWindSector(sector: WindRoseSector): void {
    console.log('[WindRose] clicked sector object:', sector);
    console.log('[WindRose] selected direction:', sector.direction);
    this.selectedWindSector = sector;
  }

  clearWindSectorSelection(): void {
    this.selectedWindSector = null;
  }

  isSelectedWindSector(sector: WindRoseSector): boolean {
    return this.selectedWindSector?.direction === sector.direction;
  }

  private buildWindRoseSectors(rawData: WindRoseData[]): WindRoseSector[] {
    console.debug('[Dashboard][WindRose] raw response', rawData);

    const dataByDirection = new Map<string, WindRoseData>();

    rawData.forEach((item) => {
      const direction = this.normalizeDirectionName(item?.direction);
      if (direction) {
        dataByDirection.set(direction, item);
      }
    });

    return this.windRoseDirections.map((direction, index) => {
      const item = dataByDirection.get(direction);
      const percentage = this.extractWindRosePercentage(item);
      const meanSpeed = this.extractNumericValue(item, ['mean_speed', 'meanSpeed', 'avg_velocity', 'average_speed']);
      const samples = this.extractNumericValue(item, ['samples', 'sample_count', 'count', 'n']);
      const angle = index * this.windRoseSectorDegrees;
      const radius = this.radiusForPercentage(percentage ?? 0);

      return {
        direction,
        percentage,
        meanSpeed,
        samples,
        velocity_range: item?.velocity_range,
        raw: item ?? null,
        angle,
        path: this.buildWindRoseSectorPath(angle, radius),
        color: this.windRosePalette[index % this.windRosePalette.length]
      };
    });
  }

  private buildWindRoseSectorPath(centerAngle: number, outerRadius: number): string {
    const startAngle = centerAngle - this.windRoseSectorDegrees / 2;
    const endAngle = centerAngle + this.windRoseSectorDegrees / 2;
    const innerStart = this.polarPoint(startAngle, this.windRoseInnerRadius);
    const outerStart = this.polarPoint(startAngle, outerRadius);
    const outerEnd = this.polarPoint(endAngle, outerRadius);
    const innerEnd = this.polarPoint(endAngle, this.windRoseInnerRadius);
    const largeArcFlag = this.windRoseSectorDegrees > 180 ? 1 : 0;

    return [
      `M ${innerStart.x} ${innerStart.y}`,
      `L ${outerStart.x} ${outerStart.y}`,
      `A ${outerRadius.toFixed(2)} ${outerRadius.toFixed(2)} 0 ${largeArcFlag} 1 ${outerEnd.x} ${outerEnd.y}`,
      `L ${innerEnd.x} ${innerEnd.y}`,
      `A ${this.windRoseInnerRadius} ${this.windRoseInnerRadius} 0 ${largeArcFlag} 0 ${innerStart.x} ${innerStart.y}`,
      'Z'
    ].join(' ');
  }

  private polarPoint(angleDegrees: number, radius: number): { x: string; y: string } {
    const radians = angleDegrees * Math.PI / 180;
    const x = this.windRoseCenter + radius * Math.sin(radians);
    const y = this.windRoseCenter - radius * Math.cos(radians);

    return {
      x: x.toFixed(2),
      y: y.toFixed(2)
    };
  }

  private radiusForPercentage(percentage: number): number {
    const maxRing = Math.max(...this.windRoseRings);
    const clamped = Math.max(0, Math.min(percentage, maxRing));
    return Math.max(this.windRoseInnerRadius, (clamped / maxRing) * this.windRoseMaxRadius);
  }

  private normalizeDirectionName(direction: unknown): string | null {
    const value = String(direction ?? '').trim().toUpperCase();
    return this.windRoseDirections.includes(value) ? value : null;
  }

  private extractWindRosePercentage(payload: unknown): number | null {
    if (typeof payload === 'number') {
      return Number.isFinite(payload) ? this.normalizePercentageScale(payload) : null;
    }

    if (!payload || typeof payload !== 'object') {
      return null;
    }

    const value = this.extractNumericValue(payload, ['percentage', 'frequency', 'value', 'freq', 'y', 'r']);

    return value === null ? null : this.normalizePercentageScale(value);
  }

  private extractNumericValue(payload: unknown, keys: string[]): number | null {
    if (typeof payload === 'number') {
      return Number.isFinite(payload) ? payload : null;
    }

    if (!payload || typeof payload !== 'object') {
      return null;
    }

    const record = payload as Record<string, unknown>;

    for (const key of keys) {
      const candidate = record[key];

      if (typeof candidate === 'number' && Number.isFinite(candidate)) {
        return candidate;
      }

      if (typeof candidate === 'string' && candidate.trim() !== '') {
        const parsed = Number(candidate);
        if (Number.isFinite(parsed)) {
          return parsed;
        }
      }

      if (candidate && typeof candidate === 'object') {
        const nestedValue = this.extractNumericValue(candidate, keys);
        if (nestedValue !== null) {
          return nestedValue;
        }
      }
    }

    return null;
  }

  private normalizePercentageScale(value: number): number {
    return value >= 0 && value <= 1 ? Number((value * 100).toFixed(2)) : Number(value.toFixed(2));
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
