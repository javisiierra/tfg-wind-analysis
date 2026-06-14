import { TestBed } from '@angular/core/testing';

import { DashboardChartService } from './dashboard-chart.service';

describe('DashboardChartService', () => {
  let service: DashboardChartService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(DashboardChartService);
  });

  it('should build monthly wind datasets with existing labels and colors', () => {
    const config = service.buildMonthlyWindChartConfig([
      { month: 1, avg_velocity: 3.2, max_velocity: 8.4, min_velocity: 1, frequency: {} },
      { month: 2, avg_velocity: 4.1, max_velocity: 9.2, min_velocity: 2, frequency: {} }
    ]);

    expect(config.type).toBe('bar');
    expect(config.data.labels).toEqual(['enero', 'febrero']);
    expect(config.data.datasets[0].label).toBe('Velocidad media (m/s)');
    expect(config.data.datasets[0].data).toEqual([3.2, 4.1]);
    expect(config.data.datasets[0].backgroundColor).toBe('rgba(37, 99, 235, .72)');
    expect(config.data.datasets[1].type).toBe('line');
    expect(config.data.datasets[1].label).toBe('Velocidad máxima (m/s)');
    expect(config.data.datasets[1].data).toEqual([8.4, 9.2]);
    expect(config.data.datasets[1].borderColor).toBe('#ef4444');
  });

  it('should keep tooltip values formatted as m/s', () => {
    const callback = service.monthlyWindChartOptions.plugins?.tooltip?.callbacks?.label;
    const label = callback?.call({} as any, {
      dataset: { label: 'Velocidad media (m/s)' },
      parsed: { y: 4.567 },
      formattedValue: '4.567'
    } as any);

    expect(label).toBe('Velocidad media (m/s): 4.57 m/s');
  });
});
