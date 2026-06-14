import { TestBed } from '@angular/core/testing';

import { DashboardDataMapperService } from './dashboard-data-mapper.service';

describe('DashboardDataMapperService', () => {
  let service: DashboardDataMapperService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(DashboardDataMapperService);
  });

  it('should create ERA5 meteo request payload without changing API contract', () => {
    expect(service.createMeteoRequestPayload(2024, '/data/case-a')).toEqual({
      year: 2024,
      case_path: '/data/case-a',
      source: 'ERA5'
    });
  });

  it('should map missing job result to dashboard defaults', () => {
    expect(service.mapJobResult(null)).toEqual({
      meteoSummary: null,
      windTimeseries: [],
      windRoseData: []
    });
  });

  it('should clamp progress and preserve normalized status response fields', () => {
    const response = service.normalizeStatusResponse({
      job_id: 'j1',
      status: 'running',
      progress: 150,
      message: null as any,
      result: undefined as any,
      error: undefined as any
    });

    expect(response.progress).toBe(100);
    expect(response.message).toBe('');
    expect(response.result).toBeNull();
    expect(response.error).toBeNull();
  });

  it('should accept boolean-like domain status from backend', () => {
    expect(service.hasDomain({ has_domain: true })).toBe(true);
    expect(service.hasDomain({ has_domain: 'true' })).toBe(true);
    expect(service.hasDomain({ has_domain: false })).toBe(false);
  });
});
