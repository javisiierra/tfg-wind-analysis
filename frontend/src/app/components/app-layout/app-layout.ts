import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterOutlet, NavigationEnd } from '@angular/router';
import { Topbar } from '../topbar/topbar';
import { Sidebar } from '../sidebar/sidebar';
import { MapContextService, DrawMode } from '../../services/map-context.service';
import { PipelineStatus } from '../topbar/topbar';
import { Subject } from 'rxjs';
import { takeUntil, filter } from 'rxjs/operators';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [CommonModule, RouterOutlet, Topbar, Sidebar],
  templateUrl: './app-layout.html',
  styleUrl: './app-layout.css'
})
export class AppLayoutComponent implements OnInit, OnDestroy {
  casePath = '';
  selectedLayer = '';
  drawMode: DrawMode = 'none';
  drawnGeometries: Record<string, any>[] = [];
  clearDrawToken = 0;
  showSidebar = true;

  pipelineStatus: PipelineStatus = {
    loading: false,
    statusText: 'Listo',
    result: null,
    error: null
  };

  private destroy$ = new Subject<void>();

  constructor(private mapContextService: MapContextService, private router: Router) {}

  ngOnInit(): void {
    // Detectar ruta actual y ocultar sidebar en dashboard
    this.checkRoute();
    this.router.events
      .pipe(
        filter(event => event instanceof NavigationEnd),
        takeUntil(this.destroy$)
      )
      .subscribe(() => this.checkRoute());

    // Subscribe to context changes
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

    this.mapContextService.drawnGeometries$
      .pipe(takeUntil(this.destroy$))
      .subscribe(geometries => {
        this.drawnGeometries = geometries;
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onCasePathChange(path: string): void {
    this.mapContextService.setCasePath(path);
  }

  onLayerSelected(layer: string): void {
    this.mapContextService.setSelectedLayer(layer);
  }

  onDrawModeChange(mode: DrawMode): void {
    this.mapContextService.setDrawMode(mode);
  }

  onGeometryChange(geometries: Record<string, any>[] | null): void {
    this.mapContextService.setDrawnGeometries(geometries ?? []);
  }

  onClearDrawing(): void {
    this.mapContextService.setDrawnGeometries([]);
    this.mapContextService.setDrawMode('none');
    this.mapContextService.setClearDrawToken(this.clearDrawToken + 1);
  }

  onCaseCreated(path: string): void {
    this.mapContextService.setCasePath(path);
    this.mapContextService.setSelectedLayer('apoyos');
  }

  onPipelineStatusChange(status: PipelineStatus): void {
    this.pipelineStatus = status;
  }

  private checkRoute(): void {
    this.showSidebar = !this.router.url.includes('/dashboard');
  }
}
