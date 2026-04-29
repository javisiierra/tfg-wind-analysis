import { Component, EventEmitter, Input, Output, OnChanges, SimpleChanges } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule, JsonPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DrawMode } from '../../app';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, JsonPipe, FormsModule],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css'
})
export class Sidebar implements OnChanges {
  @Input() casePath: string = '';
  @Input() drawnGeometry: Record<string, any> | null = null;

  @Output() layerSelected = new EventEmitter<string>();
  @Output() drawModeChange = new EventEmitter<DrawMode>();
  @Output() clearDrawing = new EventEmitter<void>();
  @Output() caseCreated = new EventEmitter<string>();

  result: any = null;
  error: any = null;
  loading = false;
  currentAction = '';

  caseName = '';

  hasDomain = false;
  hasWeatherData = false;
  hasDem = false;
  hasApoyos = false;
  hasVanos = false;
  readyForWindNinja = false;

  constructor(private http: HttpClient) {}

  ngOnChanges(changes: SimpleChanges) {
    if (changes['casePath']) {
      this.refreshCaseStatus();
    }
  }

  refreshCaseStatus() {
    if (!this.casePath) {
      this.hasDomain = false;
      this.hasWeatherData = false;
      this.hasDem = false;
      this.hasApoyos = false;
      this.hasVanos = false;
      this.readyForWindNinja = false;
      return;
    }

    this.http.post<any>('http://127.0.0.1:8000/api/v1/case/status', {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.hasDomain = !!res.has_domain;
        this.hasWeatherData = !!res.has_weather;
        this.hasDem = !!res.has_dem;
        this.hasApoyos = !!res.has_apoyos;
        this.hasVanos = !!res.has_vanos;
        this.readyForWindNinja = !!res.ready_for_windninja;
      },
      error: (err) => {
        console.error('Error consultando estado del caso:', err);
        this.hasDomain = false;
        this.hasWeatherData = false;
        this.hasDem = false;
        this.hasApoyos = false;
        this.hasVanos = false;
        this.readyForWindNinja = false;
      }
    });
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

  runRename() {
    this.call('/run-rename', 'Rename');
  }

  runWindRose() {
    this.call('/run-wind-rose', 'Wind Rose');
  }

  runWorstSupports() {
    this.callAnalysis('/worst-supports', 'Peores apoyos');
  }

  startRectangleDraw() {
    this.drawModeChange.emit('rectangle');
  }

  startPolygonDraw() {
    this.drawModeChange.emit('polygon');
  }

  clearDrawnGeometry() {
    this.clearDrawing.emit();
  }

  saveCase() {
    const trimmedName = this.caseName.trim();

    if (!trimmedName) {
      this.error = { message: 'Debes indicar un case_name.' };
      return;
    }

    if (!this.drawnGeometry) {
      this.error = { message: 'Debes dibujar un dominio antes de guardar.' };
      return;
    }

    this.loading = true;
    this.result = null;
    this.error = null;
    this.currentAction = 'Guardar caso';

    this.http.post('http://127.0.0.1:8000/api/v1/domain/create', {
      case_name: trimmedName,
      geometry: this.drawnGeometry,
      epsg: 4326
    }).subscribe({
      next: (res: any) => {
        this.result = res;
        this.loading = false;

        if (res?.case_path) {
          this.caseCreated.emit(res.case_path);
          this.layerSelected.emit('dominio');

          setTimeout(() => {
            this.refreshCaseStatus();
          }, 100);
        }
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
      }
    });
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
    this.currentAction = action;

    this.http.post(`http://127.0.0.1:8000/api/v1/pipeline${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.refreshCaseStatus();
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.refreshCaseStatus();
      }
    });
  }

  private callDomain(endpoint: string, action: string) {
    this.loading = true;
    this.result = null;
    this.error = null;
    this.currentAction = action;

    this.http.post(`http://127.0.0.1:8000/api/v1/domain${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.refreshCaseStatus();
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.refreshCaseStatus();
      }
    });
  }

  private callAnalysis(endpoint: string, action: string) {
    this.loading = true;
    this.result = null;
    this.error = null;
    this.currentAction = action;

    this.http.post(`http://127.0.0.1:8000/api/v1/analysis${endpoint}`, {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
        this.refreshCaseStatus();
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
        this.refreshCaseStatus();
      }
    });
  }
}