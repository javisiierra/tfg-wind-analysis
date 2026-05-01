import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MapComponent } from '../map/map';
import { MapContextService, DrawMode } from '../../services/map-context.service';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

@Component({
  selector: 'app-map-wrapper',
  standalone: true,
  imports: [CommonModule, MapComponent],
  templateUrl: './map-wrapper.html',
  styleUrl: './map-wrapper.css'
})
export class MapWrapperComponent implements OnInit, OnDestroy {
  casePath: string = '';
  selectedLayer: string = '';
  drawMode: DrawMode = 'none';
  clearDrawToken: number = 0;

  private destroy$ = new Subject<void>();

  constructor(private mapContextService: MapContextService) {}

  ngOnInit(): void {
    this.mapContextService.casePath$
      .pipe(takeUntil(this.destroy$))
      .subscribe(path => {
        this.casePath = path;
      });

    this.mapContextService.selectedLayer$
      .pipe(takeUntil(this.destroy$))
      .subscribe(layer => {
        this.selectedLayer = layer;
      });

    this.mapContextService.drawMode$
      .pipe(takeUntil(this.destroy$))
      .subscribe(mode => {
        this.drawMode = mode;
      });

    this.mapContextService.clearDrawToken$
      .pipe(takeUntil(this.destroy$))
      .subscribe(token => {
        this.clearDrawToken = token;
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onGeometryChange(geometries: Record<string, any>[] | null): void {
    this.mapContextService.setDrawnGeometries(geometries ?? []);
  }
}
