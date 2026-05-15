import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { DashboardService } from './dashboard.service';

describe('DashboardService', () => {
  let service: DashboardService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });
    service = TestBed.inject(DashboardService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('should call start endpoint with payload', () => {
    const payload = { year: 2024, case_path: '/tmp/case' };
    service.startMeteoSummary(payload).subscribe((res) => {
      expect(res.job_id).toBe('j1');
    });

    const req = httpMock.expectOne((r) => r.url.includes('/dashboard/meteo-summary/start'));
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    req.flush({ job_id: 'j1', status: 'queued' });
  });

  it('should propagate errors from case status', () => {
    service.getCaseStatus('/a').subscribe({
      next: () => { throw new Error('expected error'); },
      error: (err) => expect(err.status).toBe(500)
    });

    const req = httpMock.expectOne((r) => r.url.includes('/case/status'));
    req.flush({ message: 'boom' }, { status: 500, statusText: 'Server Error' });
  });
});
