import { ChangeDetectorRef, Component, NgZone, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { Chart } from 'chart.js';

import { DashboardAsyncStatusResponse, DashboardService } from '../../services/dashboard.service';
import { MapContextService } from '../../services/map-context.service';
import {
  DashboardJobStatus,
  MeteoSummaryDTO,
  WindRoseDTO,
  WindTimeseriesDTO
} from '../../models/api-contracts';
import { DashboardChartService } from '../../services/dashboard-chart.service';
import { DashboardDataMapperService } from '../../services/dashboard-data-mapper.service';
import { DashboardJobStateService } from '../../services/dashboard-job-state.service';
import { DashboardPollingService } from '../../services/dashboard-polling.service';
import { WindRosePresenterService, WindRoseSector } from '../../services/wind-rose-presenter.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
  providers: [DashboardPollingService]
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

  meteoSummary: MeteoSummaryDTO | null = null;
  windTimeseries: WindTimeseriesDTO[] = [];
  windRoseData: WindRoseDTO[] = [];
  windRoseSectors: WindRoseSector[] = [];
  selectedWindSector: WindRoseSector | null = null;

  chartContainerId = 'monthly-wind-chart';
  readonly windRoseDirections: string[];
  readonly windRoseRings: number[];

  private analysisStartedAtMs: number | null = null;
  private monthlyChart: Chart | null = null;
  private destroy$ = new Subject<void>();
  private readonly baseCasesPath = '/data';

  constructor(
    private readonly dashboardService: DashboardService,
    private readonly mapContextService: MapContextService,
    private readonly zone: NgZone,
    private readonly cdr: ChangeDetectorRef,
    private readonly polling: DashboardPollingService,
    private readonly jobState: DashboardJobStateService,
    private readonly charts: DashboardChartService,
    private readonly windRosePresenter: WindRosePresenterService,
    private readonly dataMapper: DashboardDataMapperService
  ) {
    this.windRoseDirections = this.windRosePresenter.directions;
    this.windRoseRings = this.windRosePresenter.rings;
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
    this.polling.stopPolling();
    this.monthlyChart?.destroy();
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

    this.resetAnalysisState();

    this.validateCasePathForAnalysis((validatedPath) => {
      if (!validatedPath) {
        this.isLoading = false;
        this.cdr.detectChanges();
        return;
      }

      const requestPayload = this.dataMapper.createMeteoRequestPayload(
        Number(this.selectedYear),
        validatedPath
      );

      this.progress = 5;
      this.progressMessage = 'Preparando análisis...';
      this.etaMessage = 'Calculando tiempo estimado...';
      this.analysisStartedAtMs = Date.now();
      this.jobStatus = 'queued';
      this.result = null;

      this.dashboardService.startMeteoSummary(requestPayload).subscribe({
        next: (response) => {
          this.polling.startPollingJobStatus(
            response.job_id,
            this.destroy$,
            (statusResponse) => this.handleJobStatus(statusResponse),
            (err) => this.handlePollingError(err)
          );
        },
        error: (err) => {
          const detail = this.dataMapper.errorDetail(err, 'Error desconocido');
          this.error = `Error al iniciar análisis: ${detail}`;
          this.canGenerateDomain = this.jobState.isDomainMissingError(detail);
          this.isLoading = false;
          this.etaMessage = '';
          this.analysisStartedAtMs = null;
          this.cdr.detectChanges();
        }
      });
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
        const detail = this.dataMapper.errorDetail(err, 'No se pudo generar el dominio.');
        this.isGeneratingDomain = false;
        this.canGenerateDomain = true;
        this.domainGenerationMessage = null;
        this.error = `No se pudo generar el dominio desde apoyos: ${detail}`;
        this.cdr.detectChanges();
      }
    });
  }

  selectWindSector(sector: WindRoseSector): void {
    this.selectedWindSector = sector;
  }

  clearWindSectorSelection(): void {
    this.selectedWindSector = null;
  }

  isSelectedWindSector(sector: WindRoseSector): boolean {
    return this.selectedWindSector?.direction === sector.direction;
  }

  getDirectionLabel(degrees: number): string {
    return this.windRosePresenter.getDirectionLabel(degrees);
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

  private initializeYears(): void {
    this.years = this.jobState.initializeYears();

    if (this.years.length > 0) {
      this.selectedYear = this.years[0];
    }
  }

  private resetAnalysisState(): void {
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
        if (!this.dataMapper.hasDomain(status)) {
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
        const detail = this.dataMapper.errorDetail(err, 'No se pudo validar el caso.');

        this.error = `No se pudo validar el case_path seleccionado: ${detail}`;
        this.canGenerateDomain = true;
        this.domainGenerationMessage = null;
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  private handlePollingError(err: any): void {
    this.zone.run(() => {
      const detail = this.dataMapper.errorDetail(err, 'No se pudo consultar el estado del análisis.');
      this.error = detail;
      this.canGenerateDomain = this.jobState.isDomainMissingError(detail);
      this.isLoading = false;
      this.etaMessage = '';
      this.analysisStartedAtMs = null;
      this.polling.stopPolling();
      this.cdr.detectChanges();
    });
  }

  private handleJobStatus(response: DashboardAsyncStatusResponse): void {
    this.zone.run(() => {
      const normalizedResponse = this.dataMapper.normalizeStatusResponse(response);
      const status = normalizedResponse.status;

      this.jobStatus = status;
      this.progress = normalizedResponse.progress;
      this.progressMessage = normalizedResponse.message;
      this.etaMessage = this.jobState.buildEtaMessage(
        this.progress,
        status,
        this.progressMessage,
        this.analysisStartedAtMs
      );
      this.result = normalizedResponse.result;
      this.error = normalizedResponse.error;

      if (this.error) {
        this.canGenerateDomain = this.jobState.isDomainMissingError(this.error);
      }

      if (this.dataMapper.isFinishedStatus(status)) {
        this.handleFinishedJob(normalizedResponse);
      }

      if (this.dataMapper.isFailedStatus(status)) {
        this.handleFailedJob(normalizedResponse);
      }

      this.cdr.detectChanges();
    });
  }

  private handleFinishedJob(response: DashboardAsyncStatusResponse): void {
    this.progress = 100;
    this.polling.stopPolling();

    const mappedResult = this.dataMapper.mapJobResult(response.result);
    this.meteoSummary = mappedResult.meteoSummary;
    this.windTimeseries = mappedResult.windTimeseries;
    this.windRoseData = mappedResult.windRoseData;
    this.windRoseSectors = this.windRosePresenter.buildWindRoseSectors(this.windRoseData);
    this.selectedWindSector = null;

    this.isLoading = false;
    this.etaMessage = '';
    this.analysisStartedAtMs = null;
    this.canGenerateDomain = false;
    this.cdr.detectChanges();
    this.renderCharts();
  }

  private handleFailedJob(response: DashboardAsyncStatusResponse): void {
    this.polling.stopPolling();

    const detail = response.error || 'El análisis no pudo completarse.';
    this.error = detail;
    this.canGenerateDomain = this.jobState.isDomainMissingError(detail);
    this.isLoading = false;
    this.etaMessage = '';
    this.analysisStartedAtMs = null;
  }

  private renderCharts(): void {
    setTimeout(() => {
      this.renderMonthlyChart();
    }, 100);
  }

  private renderMonthlyChart(): void {
    const canvas = document.getElementById(this.chartContainerId) as HTMLCanvasElement | null;
    if (!canvas) return;

    this.monthlyChart = this.charts.renderMonthlyChart(
      canvas,
      this.windTimeseries,
      this.monthlyChart
    );
  }
}
