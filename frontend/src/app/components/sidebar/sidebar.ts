import { Component, EventEmitter, Input, Output } from '@angular/core';
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
export class Sidebar {
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

  constructor(private http: HttpClient) {}

  runWindNinja() {
    this.call('/run-windninja', 'WindNinja');
  }

  runRename() {
    this.call('/run-rename', 'Rename');
  }

  runWindRose() {
    this.call('/run-wind-rose', 'Wind Rose');
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
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
      }
    });
  }
}
