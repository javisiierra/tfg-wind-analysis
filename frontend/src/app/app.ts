import { Component } from '@angular/core';
import { JsonPipe } from '@angular/common';
import { Topbar } from './components/topbar/topbar';
import { Sidebar } from './components/sidebar/sidebar';
import { MapComponent } from './components/map/map';
import { PipelineStatus } from './components/topbar/topbar';

export type DrawMode = 'none' | 'support';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [Topbar, Sidebar, MapComponent, JsonPipe],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  casePath = '';
  selectedLayer = '';
  drawMode: DrawMode = 'none';

  drawnGeometry: Record<string, any> | null = null;
  clearDrawToken = 0;

  pipelineStatus: PipelineStatus = {
    loading: false,
    statusText: 'Listo',
    result: null,
    error: null
  };

  onCasePathChange(path: string): void {
    this.casePath = path;
  }

  onDrawModeChange(mode: DrawMode): void {
    this.drawMode = mode;
  }

  onGeometryChange(geometry: Record<string, any> | null): void {
    this.drawnGeometry = geometry;
  }

  onClearDrawing(): void {
    this.drawnGeometry = null;
    this.drawMode = 'none';
    this.clearDrawToken += 1;
  }

  onCaseCreated(path: string): void {
    this.casePath = path;
    this.selectedLayer = 'apoyos';
  }

  onPipelineStatusChange(status: PipelineStatus): void {
    this.pipelineStatus = status;
  }
}