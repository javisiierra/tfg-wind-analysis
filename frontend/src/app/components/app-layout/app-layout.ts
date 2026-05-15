import { ChangeDetectorRef, Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { Topbar } from '../topbar/topbar';
import { Sidebar } from '../sidebar/sidebar';
import { MapContextService, DrawMode } from '../../services/map-context.service';
import { PipelineStatus } from '../topbar/topbar';
import { CaseStatusResponse, DashboardService } from '../../services/dashboard.service';
import { Subject, finalize } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [CommonModule, RouterOutlet, Topbar, Sidebar],
  templateUrl: './app-layout.html',
  styleUrl: './app-layout.css'
})
export class AppLayoutComponent implements OnInit, OnDestroy {
  casePath = '';
  caseStatus: CaseStatusResponse | null = null;
  isCaseStatusLoading = false;
  selectedLayer = '';
  drawMode: DrawMode = 'none';
  drawnGeometries: Record<string, any>[] = [];
  clearDrawToken = 0;

  pipelineStatus: PipelineStatus = {
    loading: false,
    statusText: 'Listo',
    result: null,
    error: null
  };

  private destroy$ = new Subject<void>();
  private caseStatusRequestId = 0;

  constructor(
    private mapContextService: MapContextService,
    private dashboardService: DashboardService,
    private changeDetectorRef: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    // Subscribe to context changes
    this.mapContextService.casePath$
      .pipe(takeUntil(this.destroy$))
      .subscribe(path => {
        const normalizedPath = path?.trim();

        if (normalizedPath === this.casePath) {
          return;
        }

        if (!normalizedPath) {
          this.casePath = '';
          this.caseStatus = null;
          this.isCaseStatusLoading = false;
          return;
        }

        this.casePath = normalizedPath;
        this.loadCaseStatus(normalizedPath);
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

  onFolderSelected(path: string): void {
    const normalizedPath = path?.trim();

    if (!normalizedPath) {
      this.casePath = '';
      this.caseStatus = null;
      this.isCaseStatusLoading = false;
      return;
    }

    this.casePath = normalizedPath;
    this.mapContextService.setCasePath(normalizedPath);

    this.loadCaseStatus(normalizedPath);
  }

  refreshActiveCaseStatus(): void {
    this.loadCaseStatus(this.casePath);
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
    this.onFolderSelected(path);
    this.mapContextService.setSelectedLayer('apoyos');
  }

  onCaseActionCompleted(path?: string): void {
    const normalizedPath = path?.trim();

    if (normalizedPath && normalizedPath !== this.casePath) {
      this.casePath = normalizedPath;
      this.mapContextService.setCasePath(normalizedPath);
    }

    this.refreshActiveCaseStatus();
    this.mapContextService.refreshSelectedLayer();
  }

  onPipelineStatusChange(status: PipelineStatus): void {
    this.pipelineStatus = status;
  }

  private loadCaseStatus(path: string): void {
    const normalizedPath = path?.trim();

    if (!normalizedPath) {
      this.caseStatus = null;
      this.isCaseStatusLoading = false;
      this.changeDetectorRef.detectChanges();
      return;
    }

    this.isCaseStatusLoading = true;
    this.caseStatus = null;
    this.changeDetectorRef.detectChanges();
    const requestId = ++this.caseStatusRequestId;

    this.dashboardService.getCaseStatus(normalizedPath)
      .pipe(
        finalize(() => {
          if (this.casePath === normalizedPath && this.caseStatusRequestId === requestId) {
            this.isCaseStatusLoading = false;
            this.changeDetectorRef.detectChanges();
          }
        })
      )
      .subscribe({
        next: (status) => {
          if (this.casePath === normalizedPath && this.caseStatusRequestId === requestId) {
            this.caseStatus = { ...status };
            this.changeDetectorRef.detectChanges();
          }
        },
        error: (error) => {
          console.error('[Layout] Error loading case status:', error);
          if (this.casePath === normalizedPath && this.caseStatusRequestId === requestId) {
            this.caseStatus = null;
            this.changeDetectorRef.detectChanges();
          }
        }
      });
  }

}
