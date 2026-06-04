import { TestBed } from '@angular/core/testing';
import { Subject, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { DashboardPollingService } from './dashboard-polling.service';
import { DashboardService } from './dashboard.service';

describe('DashboardPollingService', () => {
  let service: DashboardPollingService;
  let dashboardService: Pick<DashboardService, 'getMeteoSummaryStatus'>;
  let destroy$: Subject<void>;

  beforeEach(() => {
    dashboardService = {
      getMeteoSummaryStatus: vi.fn().mockReturnValue(of({
        job_id: 'j1',
        status: 'running',
        progress: 25,
        message: 'Procesando',
        result: null,
        error: null
      }))
    };

    TestBed.configureTestingModule({
      providers: [
        DashboardPollingService,
        { provide: DashboardService, useValue: dashboardService }
      ]
    });
    service = TestBed.inject(DashboardPollingService);
    destroy$ = new Subject<void>();
  });

  afterEach(() => {
    service.stopPolling();
    destroy$.next();
    destroy$.complete();
  });

  it('should fetch job status immediately and mark job as active', () => {
    const onStatus = vi.fn();

    service.startPollingJobStatus('j1', destroy$, onStatus, vi.fn());

    expect(dashboardService.getMeteoSummaryStatus).toHaveBeenCalledWith('j1');
    expect(onStatus).toHaveBeenCalledWith(expect.objectContaining({ job_id: 'j1', progress: 25 }));
    expect(service.hasActiveJob()).toBe(true);
  });

  it('should route polling errors to the provided handler', () => {
    const error = new Error('boom');
    (dashboardService.getMeteoSummaryStatus as any).mockReturnValue(throwError(() => error));
    const onError = vi.fn();

    service.startPollingJobStatus('j1', destroy$, vi.fn(), onError);

    expect(onError).toHaveBeenCalledWith(error);
  });

  it('should stop polling and clear active job', () => {
    service.startPollingJobStatus('j1', destroy$, vi.fn(), vi.fn());

    service.stopPolling();

    expect(service.hasActiveJob()).toBe(false);
  });
});
