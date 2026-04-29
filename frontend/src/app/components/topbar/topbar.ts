import { Component, EventEmitter, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';

export interface PipelineStatus {
  loading: boolean;
  statusText: string;
  result: any | null;
  error: any | null;
}

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [FormsModule, CommonModule],
  templateUrl: './topbar.html',
  styleUrl: './topbar.css',
})
export class Topbar {
  casePath = '';

  private readonly baseCasesPath = 'C:\\Datos_TFG';

  @Output() caseChange = new EventEmitter<string>();
  @Output() pipelineStatusChange = new EventEmitter<PipelineStatus>();

  result: any = null;
  error: any = null;
  loading = false;

  constructor(private http: HttpClient) {}

  async selectFolder() {
    try {
      const dirHandle = await (window as any).showDirectoryPicker();

      this.casePath = `${this.baseCasesPath}\\${dirHandle.name}`;
      this.caseChange.emit(this.casePath);
      this.emitPipelineStatus();
    } catch (err) {
      console.error('Selección de carpeta cancelada o no soportada:', err);
    }
  }

  runBase() {
    this.caseChange.emit(this.casePath);

    this.loading = true;
    this.result = null;
    this.error = null;
    this.emitPipelineStatus();

    this.http.post('http://127.0.0.1:8000/api/v1/pipeline/run-base', {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.emitPipelineStatus();
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.emitPipelineStatus();
      }
    });
  }

  private emitPipelineStatus(): void {
    this.pipelineStatusChange.emit({
      loading: this.loading,
      statusText: this.statusText,
      result: this.result,
      error: this.error
    });
  }

  get statusText(): string {
    if (this.loading) return 'Ejecutando pipeline base...';
    if (this.error) return 'Error en la ejecución';
    if (this.result) return 'Pipeline base completado';
    return 'Listo';
  }
}