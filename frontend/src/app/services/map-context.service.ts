import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export type DrawMode = 'none' | 'support';

@Injectable({
  providedIn: 'root'
})
export class MapContextService {
  private casePathSubject = new BehaviorSubject<string>('');
  private selectedLayerSubject = new BehaviorSubject<string>('');
  private drawModeSubject = new BehaviorSubject<DrawMode>('none');
  private clearDrawTokenSubject = new BehaviorSubject<number>(0);
  private layerRefreshTokenSubject = new BehaviorSubject<number>(0);
  private drawnGeometriesSubject = new BehaviorSubject<Record<string, any>[]>([]);

  casePath$ = this.casePathSubject.asObservable();
  selectedLayer$ = this.selectedLayerSubject.asObservable();
  drawMode$ = this.drawModeSubject.asObservable();
  clearDrawToken$ = this.clearDrawTokenSubject.asObservable();
  layerRefreshToken$ = this.layerRefreshTokenSubject.asObservable();
  drawnGeometries$ = this.drawnGeometriesSubject.asObservable();

  constructor() {}

  setCasePath(path: string): void {
    this.casePathSubject.next(path);
  }

  setSelectedLayer(layer: string): void {
    this.selectedLayerSubject.next(layer);
  }

  setDrawMode(mode: DrawMode): void {
    this.drawModeSubject.next(mode);
  }

  setClearDrawToken(token: number): void {
    this.clearDrawTokenSubject.next(token);
  }

  refreshSelectedLayer(): void {
    this.layerRefreshTokenSubject.next(this.layerRefreshTokenSubject.value + 1);
  }

  setDrawnGeometries(geometries: Record<string, any>[]): void {
    this.drawnGeometriesSubject.next(geometries);
  }

  getCasePath(): string {
    return this.casePathSubject.value;
  }

  getSelectedLayer(): string {
    return this.selectedLayerSubject.value;
  }

  getDrawMode(): DrawMode {
    return this.drawModeSubject.value;
  }
}
