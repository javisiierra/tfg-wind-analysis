import { Component, EventEmitter, Input, NgZone, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ExecutionUiState } from '../../models/execution-ui-state';
import { DashboardService } from '../../services/dashboard.service';

type PipelineStepResponse = Record<string, unknown> & {
  status?: string;
  ok?: boolean;
};

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [FormsModule, CommonModule],
  templateUrl: './topbar.html',
  styleUrl: './topbar.css',
})
export class Topbar {
  @Input() casePath = '';
  @Input() isExecutionRunning = false;

  private readonly baseCasesPath = '/data';
  private readonly apiUrl = environment.apiUrl;

  @Output() folderSelected = new EventEmitter<string>();
  @Output() casePrepared = new EventEmitter<string>();
  @Output() preparationCompleted = new EventEmitter<string>();
  @Output() executionUiStateChange = new EventEmitter<ExecutionUiState>();

  result: any = null;
  error: any = null;
  loading = false;
  private currentPipelineStage: string | undefined;

  constructor(
    private http: HttpClient,
    private dashboardService: DashboardService,
    private ngZone: NgZone
  ) {}

  onCasePathInputChange(path: string): void {
    this.casePath = path;
    this.folderSelected.emit(path);
  }

  async selectFolder() {
    try {
      const dirHandle = await (window as any).showDirectoryPicker();

      this.ngZone.run(() => {
        this.casePath = `${this.baseCasesPath}/${dirHandle.name}`;
        this.folderSelected.emit(this.casePath);

        this.result = null;
        this.error = null;
        this.loading = false;

        this.executionUiStateChange.emit({
          status: 'idle',
          title: 'Listo'
        });
      });
    } catch (err) {
      console.error('Seleccion de carpeta cancelada o no soportada:', err);
    }
  }

  prepareCase() {
    if (!this.casePath) {
      this.error = { message: 'Selecciona una carpeta primero' };
      this.emitErrorState(this.error.message);
      return;
    }

    this.loading = true;
    this.result = null;
    this.error = null;
    this.executionUiStateChange.emit({
      status: 'running',
      title: 'Importando carpeta...',
      stage: 'Importando carpeta',
      detail: 'Adaptando la carpeta externa al formato del caso'
    });

    this.http.post(`${this.apiUrl}/case/import-folder`, {
      input_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.casePrepared.emit(this.casePath);
        this.executionUiStateChange.emit({
          status: 'success',
          title: 'Listo',
          detail: 'Carpeta importada correctamente'
        });
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.emitErrorState(this.getErrorDetail(err, 'No se pudo importar la carpeta.'));
      }
    });
  }

  async executePreparationPipeline(): Promise<void> {
    if (!this.casePath) {
      this.error = { message: 'Selecciona o crea un caso primero' };
      this.emitErrorState(this.error.message, 'Validando caso');
      return;
    }

    this.loading = true;
    this.result = null;
    this.error = null;

    try {
      await this.runStep(
        'Preparando dominio, DEM y meteorologia',
        45,
        () => firstValueFrom(this.dashboardService.runPreparation(this.casePath))
      );

      const windninjaResult = await this.runStep(
        'Ejecutando WindNinja y postprocesado',
        90,
        () => firstValueFrom(this.dashboardService.runWindNinja(this.casePath))
      );

      this.result = windninjaResult;
      this.loading = false;
      this.currentPipelineStage = undefined;
      this.executionUiStateChange.emit({
        status: 'success',
        title: 'Preparacion completada',
        stage: 'Finalizado',
        progress: 100,
        detail: 'Pipeline moderno completado correctamente'
      });
      this.preparationCompleted.emit(this.casePath);
    } catch (err) {
      this.error = err;
      this.loading = false;
      this.emitErrorState(
        this.getErrorDetail(err, 'No se pudo ejecutar la preparacion.'),
        this.getFailedStage(err)
      );
      console.error('[Ejecutar preparacion] Error:', err);
    }
  }

  private async runStep(
    stage: string,
    progress: number,
    action: () => Promise<PipelineStepResponse>
  ): Promise<PipelineStepResponse> {
    this.emitRunningState(stage, progress);
    const response = await action();

    if (!this.hasOkStatus(response)) {
      throw {
        stage,
        error: {
          detail: `La etapa "${stage}" no devolvio un estado correcto.`
        },
        response
      };
    }

    return response;
  }

  private emitRunningState(stage: string, progress: number, detail?: string): void {
    this.currentPipelineStage = stage;
    this.executionUiStateChange.emit({
      status: 'running',
      title: 'Ejecutando preparacion...',
      stage,
      progress,
      detail
    });
  }

  private hasOkStatus(response: PipelineStepResponse): boolean {
    return response.ok === true || response.status === 'ok' || response.status === 'ready';
  }

  private emitErrorState(detail: string, stage?: string): void {
    this.executionUiStateChange.emit({
      status: 'error',
      title: 'Error',
      stage,
      detail
    });
  }

  private getErrorDetail(error: any, fallback: string): string {
    const detail = error?.error?.detail ?? error?.message ?? error?.response?.error?.detail;

    if (typeof detail === 'string') {
      return detail;
    }

    if (detail?.message) {
      return detail.message;
    }

    return fallback;
  }

  private getFailedStage(error: any): string | undefined {
    return error?.stage || this.currentPipelineStage;
  }
}
