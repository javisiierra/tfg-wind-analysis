import { Component, EventEmitter, Input, NgZone, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { environment } from '../../../environments/environment';

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
  @Input() casePath = '';

  private readonly baseCasesPath = '/data';
  private readonly apiBaseUrl = environment.apiBaseUrl;

  @Output() folderSelected = new EventEmitter<string>();
  @Output() casePrepared = new EventEmitter<string>();
  @Output() pipelineStatusChange = new EventEmitter<PipelineStatus>();

  result: any = null;
  error: any = null;
  loading = false;
  currentStep = '';

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
        this.currentStep = '';

        this.emitPipelineStatus();
      });
    } catch (err) {
      console.error('Selección de carpeta cancelada o no soportada:', err);
    }
  }

  prepareCase() {
  if (!this.casePath) {
    this.error = { message: 'Selecciona una carpeta primero' };
    this.emitPipelineStatus();
    return;
  }

  this.loading = true;
  this.result = null;
  this.error = null;
  this.emitPipelineStatus();

  this.http.post(`${this.apiBaseUrl}/case/import-folder`, {
    input_path: this.casePath
  }).subscribe({
    next: (res) => {
      this.result = res;
      this.loading = false;
      this.casePrepared.emit(this.casePath);
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
    if (this.loading) return this.currentStep || 'Preparando caso...';
    if (this.error) return 'Error en la preparación';
    if (this.result) return 'Caso preparado correctamente';
    return 'Listo';
  }
}
