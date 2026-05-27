import { Component, EventEmitter, Input, NgZone, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { environment } from '../../../environments/environment';
import { ExecutionUiState } from '../../models/execution-ui-state';

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
  private readonly apiBaseUrl = environment.apiBaseUrl;

  @Output() folderSelected = new EventEmitter<string>();
  @Output() casePrepared = new EventEmitter<string>();
  @Output() executionUiStateChange = new EventEmitter<ExecutionUiState>();

  result: any = null;
  error: any = null;
  loading = false;

  constructor(
    private http: HttpClient,
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
      console.error('Selección de carpeta cancelada o no soportada:', err);
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
      title: 'Ejecutando preparar caso...',
      stage: 'Importando carpeta',
      detail: 'Preparando entradas del caso activo'
    });

    this.http.post(`${this.apiBaseUrl}/case/import-folder`, {
      input_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.casePrepared.emit(this.casePath);
        this.executionUiStateChange.emit({
          status: 'success',
          title: 'Listo',
          detail: 'Última ejecución completada correctamente'
        });
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.emitErrorState(this.getErrorDetail(err));
      }
    });
  }

  private emitErrorState(detail: string): void {
    this.executionUiStateChange.emit({
      status: 'error',
      title: 'Error',
      detail
    });
  }

  private getErrorDetail(error: any): string {
    return error?.error?.detail || error?.message || 'No se pudo preparar el caso.';
  }
}
