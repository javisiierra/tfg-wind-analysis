import { Component, EventEmitter, Input, Output } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule, JsonPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DrawMode } from '../../app';
import { CaseStatusResponse } from '../../services/dashboard.service';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, JsonPipe, FormsModule],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css'
})
export class Sidebar {
  @Input() casePath: string = '';
  @Input() caseStatus: CaseStatusResponse | null = null;
  @Input() isCaseStatusLoading = false;
  @Input() drawnGeometries: Record<string, any>[] = [];

  @Output() layerSelected = new EventEmitter<string>();
  @Output() drawModeChange = new EventEmitter<DrawMode>();
  @Output() clearDrawing = new EventEmitter<void>();
  @Output() caseCreated = new EventEmitter<string>();
  @Output() actionCompletedOk = new EventEmitter<string | undefined>();

  result: any = null;
  error: any = null;
  userMessage = '';
  loading = false;
  currentAction = '';

  caseName = '';

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
      return;
    }

    if (!this.drawnGeometries.length) {
      this.error = { message: 'Debes dibujar al menos un apoyo antes de guardar.' };
      return;
    }

    this.loading = true;
    this.result = null;
    this.error = null;
    this.userMessage = '';
    this.currentAction = 'Guardar apoyos';

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
          'http://127.0.0.1:8000/api/v1/supports/create',
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
    } catch (err) {
      this.error = err;
      this.loading = false;
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

    this.http.post(`http://127.0.0.1:8000/api/v1/pipeline${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.userMessage = this.buildPipelineUserMessage(endpoint, res);
        this.loading = false;
        this.actionCompletedOk.emit(this.casePath);
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
      }
    });
  }

  private callDomain(endpoint: string, action: string) {
    this.loading = true;
    this.result = null;
    this.error = null;
    this.userMessage = '';
    this.currentAction = action;

    this.http.post(`http://127.0.0.1:8000/api/v1/domain${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.actionCompletedOk.emit(this.casePath);

        if (endpoint === '/generate-dem') {
          this.layerSelected.emit('dominio');
        }
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
      }
    });
  }

  private callVanos(endpoint: string, action: string) {
    this.loading = true;
    this.result = null;
    this.error = null;
    this.currentAction = action;

    this.http.post(`http://127.0.0.1:8000/api/v1/vanos${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.actionCompletedOk.emit(this.casePath);
        this.layerSelected.emit('vanos');
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
      }
    });
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
