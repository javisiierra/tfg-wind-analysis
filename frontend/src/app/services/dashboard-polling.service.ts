import { Injectable } from '@angular/core';
import { Subject, Subscription, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { DashboardAsyncStatusResponse, DashboardService } from './dashboard.service';

@Injectable({
  providedIn: 'root'
})
export class DashboardPollingService {
  private pollingSubscription: Subscription | null = null;
  private activeJobId: string | null = null;

  constructor(private readonly dashboardService: DashboardService) {}

  startPollingJobStatus(
    jobId: string,
    destroy$: Subject<void>,
    onStatus: (response: DashboardAsyncStatusResponse) => void,
    onError: (err: any) => void
  ): void {
    this.stopPolling();
    this.activeJobId = jobId;
    this.fetchJobStatus(jobId, onStatus, onError);

    this.pollingSubscription = interval(2500)
      .pipe(takeUntil(destroy$))
      .subscribe(() => {
        if (!this.activeJobId) return;
        this.fetchJobStatus(jobId, onStatus, onError);
      });
  }

  stopPolling(): void {
    this.pollingSubscription?.unsubscribe();
    this.pollingSubscription = null;
    this.activeJobId = null;
  }

  clearActiveJob(): void {
    this.activeJobId = null;
  }

  hasActiveJob(): boolean {
    return this.activeJobId !== null;
  }

  private fetchJobStatus(
    jobId: string,
    onStatus: (response: DashboardAsyncStatusResponse) => void,
    onError: (err: any) => void
  ): void {
    this.dashboardService.getMeteoSummaryStatus(jobId).subscribe({
      next: onStatus,
      error: onError
    });
  }
}
