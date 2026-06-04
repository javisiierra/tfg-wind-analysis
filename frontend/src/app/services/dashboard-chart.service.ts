import { Injectable } from '@angular/core';
import { Chart, ChartConfiguration, ChartOptions, registerables } from 'chart.js';
import { WindTimeseriesDTO } from '../models/api-contracts';

Chart.register(...registerables);

@Injectable({
  providedIn: 'root'
})
export class DashboardChartService {
  readonly monthlyWindChartOptions: ChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'nearest',
      intersect: false
    },
    hover: {
      mode: 'nearest',
      intersect: false
    },
    plugins: {
      legend: {
        position: 'top'
      },
      tooltip: {
        enabled: true,
        mode: 'nearest',
        intersect: false,
        callbacks: {
          title: (items) => items[0]?.label ?? '',
          label: (context) => {
            const label = context.dataset.label ?? '';
            const value = typeof context.parsed.y === 'number'
              ? context.parsed.y.toFixed(2)
              : context.formattedValue;

            return `${label}: ${value} m/s`;
          }
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: 'm/s'
        }
      }
    }
  };

  buildMonthlyWindChartConfig(windTimeseries: WindTimeseriesDTO[]): ChartConfiguration {
    const labels = windTimeseries.map(data =>
      new Intl.DateTimeFormat('es-ES', { month: 'long' }).format(new Date(2024, data.month - 1))
    );

    const avgData = windTimeseries.map(data => data.avg_velocity);
    const maxData = windTimeseries.map(data => data.max_velocity);

    return {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Velocidad media (m/s)',
            data: avgData,
            backgroundColor: 'rgba(37, 99, 235, .72)',
            borderColor: '#60a5fa',
            borderWidth: 1,
            hoverBackgroundColor: 'rgba(37, 99, 235, .92)'
          },
          {
            label: 'Velocidad mÃ¡xima (m/s)',
            data: maxData,
            type: 'line',
            tension: 0.3,
            borderColor: '#ef4444',
            backgroundColor: '#ef4444',
            pointBackgroundColor: '#ef4444',
            pointBorderColor: '#fecaca',
            pointRadius: 4,
            pointHoverRadius: 6
          }
        ]
      },
      options: this.monthlyWindChartOptions
    };
  }

  renderMonthlyChart(
    canvas: HTMLCanvasElement,
    windTimeseries: WindTimeseriesDTO[],
    existingChart: Chart | null
  ): Chart {
    existingChart?.destroy();
    return new Chart(canvas, this.buildMonthlyWindChartConfig(windTimeseries));
  }
}
