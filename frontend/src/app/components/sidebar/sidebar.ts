import { Component, EventEmitter, Input, Output } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DrawMode } from '../../app';
import { CaseStatusResponse } from '../../services/dashboard.service';
import { ExecutionUiState } from '../../models/execution-ui-state';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css'
})
export class Sidebar {
  @Input() casePath: string = '';
  @Input() caseStatus: CaseStatusResponse | null = null;
  @Input() isCaseStatusLoading = false;
  @Input() isExecutionRunning = false;
  @Input() drawnGeometries: Record<string, any>[] = [];

  @Output() layerSelected = new EventEmitter<string>();
  @Output() drawModeChange = new EventEmitter<DrawMode>();
  @Output() clearDrawing = new EventEmitter<void>();
  @Output() caseCreated = new EventEmitter<string>();
  @Output() actionCompletedOk = new EventEmitter<string | undefined>();
  @Output() executionUiStateChange = new EventEmitter<ExecutionUiState>();

  result: any = null;
  error: any = null;
  userMessage = '';
  loading = false;
  currentAction = '';

  caseName = '';
  private readonly apiUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  startSupportDraw() {
    this.drawModeChange.emit('support');
  }

  finishSupportDraw() {
    this.drawModeChange.emit('none');
  }

  clearDrawnGeometry() {
    this.clearDrawing.emit();
  }

  async saveCase() {
    const trimmedName = this.caseName.trim();

    if (!trimmedName && !this.casePath) {
      this.error = { message: 'Debes indicar un case_name o tener un caso activo.' };
      this.emitErrorState(this.error.message);
      return;
    }

    if (!this.drawnGeometries.length) {
      this.error = { message: 'Debes dibujar al menos un apoyo antes de guardar.' };
      this.emitErrorState(this.error.message);
      return;
    }

    this.loading = true;
    this.result = null;
    this.error = null;
    this.userMessage = '';
    this.currentAction = 'Guardar apoyos';
    this.emitRunningState('Guardar apoyos', 'Persistiendo geometria y actualizando el caso');

    try {
      let lastResponse: any = null;

      for (const geometry of this.drawnGeometries) {
        const payload: any = {
          geometry,
          epsg: 4326
        };

        if (this.casePath) {
          payload.case_path = this.casePath;
        } else {
          payload.case_name = trimmedName;
        }

        lastResponse = await this.http.post(
          `${this.apiUrl}/supports/create`,
          payload
        ).toPromise();
      }

      this.result = {
        status: 'ok',
        message: `Guardados ${this.drawnGeometries.length} apoyos.`,
        last_response: lastResponse
      };

      if (lastResponse?.case_path) {
        this.caseCreated.emit(lastResponse.case_path);
      } else {
        this.actionCompletedOk.emit(this.casePath || undefined);
      }

      this.layerSelected.emit('apoyos');
      this.clearDrawing.emit();

      this.loading = false;
      this.emitSuccessState();
    } catch (err) {
      this.error = err;
      this.loading = false;
      this.emitErrorState(this.getErrorDetail(err, 'No se pudieron guardar los apoyos.'));
    }
  }

  runGenerateDomainFromSupports() {
    this.callDomain('/generate-from-supports', 'Generar dominio desde apoyos');
  }

  runGenerateVanosFromSupports() {
    this.callVanos('/generate-from-supports', 'Generar vanos desde apoyos');
  }

  runGenerateDem() {
    this.callDomain('/generate-dem', 'Generar DEM');
  }

  runGenerateWeather() {
    this.callDomain('/generate-weather', 'Generar meteorología');
  }

  runWindNinja() {
    this.call('/run-windninja', 'WindNinja');
  }

  showApoyos() {
    this.layerSelected.emit('apoyos');
  }

  showVanos() {
    this.layerSelected.emit('vanos');
  }

  showDominio() {
    this.layerSelected.emit('dominio');
  }

  showWorstSupports() {
    this.layerSelected.emit('worst');
  }

  private call(endpoint: string, action: string) {
    this.loading = true;
    this.result = null;
    this.error = null;
    this.userMessage = '';
    this.currentAction = action;
    this.emitRunningState(action, this.detailForAction(action));

    this.http.post(`${this.apiUrl}/pipeline${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.userMessage = this.buildPipelineUserMessage(endpoint, res);
        this.loading = false;
        this.emitSuccessState(this.userMessage || undefined);
        this.actionCompletedOk.emit(this.casePath);
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.emitErrorState(this.getErrorDetail(err, `Error ejecutando ${action}.`));
      }
    });
  }

  private callDomain(endpoint: string, action: string) {
    this.loading = true;
    this.result = null;
    this.error = null;
    this.userMessage = '';
    this.currentAction = action;
    this.emitRunningState(action, this.detailForAction(action));

    this.http.post(`${this.apiUrl}/domain${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.emitSuccessState();
        this.actionCompletedOk.emit(this.casePath);

        if (endpoint === '/generate-dem') {
          this.layerSelected.emit('dominio');
        }
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.emitErrorState(this.getErrorDetail(err, `Error ejecutando ${action}.`));
      }
    });
  }

  private callVanos(endpoint: string, action: string) {
    this.loading = true;
    this.result = null;
    this.error = null;
    this.currentAction = action;
    this.emitRunningState(action, this.detailForAction(action));

    this.http.post(`${this.apiUrl}/vanos${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.emitSuccessState();
        this.actionCompletedOk.emit(this.casePath);
        this.layerSelected.emit('vanos');
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.emitErrorState(this.getErrorDetail(err, `Error ejecutando ${action}.`));
      }
    });
  }

  private emitRunningState(action: string, detail?: string): void {
    this.executionUiStateChange.emit({
      status: 'running',
      title: `Ejecutando ${action}...`,
      stage: action,
      detail
    });
  }

  private emitSuccessState(detail = 'Última ejecución completada correctamente'): void {
    this.executionUiStateChange.emit({
      status: 'success',
      title: 'Listo',
      detail
    });
  }

  private emitErrorState(detail: string): void {
    this.executionUiStateChange.emit({
      status: 'error',
      title: 'Error',
      detail
    });
  }

  private getErrorDetail(error: any, fallback: string): string {
    return error?.error?.detail || error?.message || fallback;
  }

  private detailForAction(action: string): string {
    const details: Record<string, string> = {
      'Guardar apoyos': 'Persistiendo geometria y actualizando el caso',
      'Generar dominio desde apoyos': 'Construyendo dominio a partir de apoyos',
      'Generar vanos desde apoyos': 'Calculando vanos entre apoyos',
      'Generar DEM': 'Descargando, recortando y reproyectando raster',
      'Generar meteorología': 'Generando ficheros meteorologicos para WindNinja',
      'WindNinja': 'Ejecutando simulacion y postprocesos'
    };

    return details[action] || `Ejecutando ${action}`;
  }

  private buildPipelineUserMessage(endpoint: string, res: any): string {
    if (endpoint !== '/run-windninja') {
      return '';
    }

    if (res?.rename_success && res?.worst_supports_success && res?.wind_rose_success) {
      return 'WindNinja finalizado. Salidas renombradas, vanos críticos y rosa de vientos generados.';
    }

    if (res?.wind_rose_warning || res?.wind_rose_success === false) {
      return 'WindNinja finalizado, pero no se pudo generar la rosa de vientos.';
    }

    if (
      res?.postprocess_warnings?.length ||
      res?.rename_warning ||
      res?.worst_supports_warning
    ) {
      return 'WindNinja finalizado, pero hubo avisos en el postproceso.';
    }

    return 'WindNinja finalizado.';
  }
}
