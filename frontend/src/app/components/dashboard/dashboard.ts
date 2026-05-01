import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DashboardService } from '../../services/dashboard.service';

interface MeteoSummary {
  year: number;
  avg_velocity: number;
  max_velocity: number;
  dominant_direction: number;
  windiest_month: number;
  viability_index: number;
  data_points: number;
}

interface WindTimeseries {
  month: number;
  avg_velocity: number;
  max_velocity: number;
  min_velocity: number;
  frequency: Record<string, number>;
}

interface WindRoseData {
  direction: string;
  frequency: number;
  velocity_range: { min: number; max: number };
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css'
})
export class DashboardComponent implements OnInit {
  years: number[] = [];
  selectedYear: number | null = null;
  isLoading = false;
  error: string | null = null;

  meteoSummary: MeteoSummary | null = null;
  windTimeseries: WindTimeseries[] = [];
  windRoseData: WindRoseData[] = [];

  chartContainerId = 'monthly-wind-chart';
  roseContainerId = 'wind-rose-chart';

  constructor(private dashboardService: DashboardService) {
    this.initializeYears();
  }

  ngOnInit(): void {
    // Chart libraries will be loaded dynamically when needed
  }

  private initializeYears(): void {
    const currentYear = new Date().getFullYear();
    this.years = [];
    for (let i = currentYear; i >= currentYear - 10; i--) {
      this.years.push(i);
    }
    if (this.years.length > 0) {
      this.selectedYear = this.years[0];
    }
  }

  onAnalysisButtonClick(): void {
    if (!this.selectedYear) {
      this.error = 'Por favor selecciona un año';
      return;
    }

    this.isLoading = true;
    this.error = null;

    this.dashboardService.getMeteoSummary(this.selectedYear).subscribe({
      next: (summary) => {
        this.meteoSummary = summary;
        this.loadWindTimeseries();
      },
      error: (err) => {
        this.error = `Error al obtener resumen meteorológico: ${err.message}`;
        this.isLoading = false;
      }
    });
  }

  private loadWindTimeseries(): void {
    if (!this.selectedYear) return;

    this.dashboardService.getWindTimeseries(this.selectedYear).subscribe({
      next: (data) => {
        this.windTimeseries = data;
        this.loadWindRose();
      },
      error: (err) => {
        this.error = `Error al obtener series temporales: ${err.message}`;
        this.isLoading = false;
      }
    });
  }

  private loadWindRose(): void {
    if (!this.selectedYear) return;

    this.dashboardService.getWindRose(this.selectedYear).subscribe({
      next: (data) => {
        this.windRoseData = data;
        this.renderCharts();
        this.isLoading = false;
      },
      error: (err) => {
        this.error = `Error al obtener rosa de vientos: ${err.message}`;
        this.isLoading = false;
      }
    });
  }

  private renderCharts(): void {
    setTimeout(() => {
      this.renderMonthlyChart();
      this.renderWindRoseChart();
    }, 100);
  }

  private renderMonthlyChart(): void {
    const container = document.getElementById(this.chartContainerId);
    if (!container) return;

    // Simple chart rendering - can be replaced with Chart.js or similar
    let html = '<div class="chart-placeholder"><p>Gráfico de viento mensual</p>';
    if (this.windTimeseries.length > 0) {
      html += '<table class="data-table"><tr><th>Mes</th><th>Vel. Media</th><th>Vel. Máx</th></tr>';
      this.windTimeseries.forEach(data => {
        const monthName = new Intl.DateTimeFormat('es-ES', { month: 'long' })
          .format(new Date(2024, data.month - 1));
        html += `<tr><td>${monthName}</td><td>${data.avg_velocity.toFixed(2)} m/s</td><td>${data.max_velocity.toFixed(2)} m/s</td></tr>`;
      });
      html += '</table>';
    }
    html += '</div>';
    container.innerHTML = html;
  }

  private renderWindRoseChart(): void {
    const container = document.getElementById(this.roseContainerId);
    if (!container) return;

    // Simple rose chart rendering - can be replaced with proper visualization library
    let html = '<div class="chart-placeholder"><p>Rosa de vientos</p>';
    if (this.windRoseData.length > 0) {
      html += '<ul class="wind-rose-list">';
      this.windRoseData.forEach(data => {
        html += `<li><strong>${data.direction}</strong>: ${(data.frequency * 100).toFixed(1)}%</li>`;
      });
      html += '</ul>';
    }
    html += '</div>';
    container.innerHTML = html;
  }

  getDirectionLabel(degrees: number): string {
    const directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
    const index = Math.round(degrees / 22.5) % 16;
    return directions[index];
  }

  getViabilityStatus(index: number): string {
    if (index >= 0.7) return 'Muy Alta';
    if (index >= 0.5) return 'Alta';
    if (index >= 0.3) return 'Media';
    return 'Baja';
  }

  getViabilityClass(index: number): string {
    if (index >= 0.7) return 'viability-high';
    if (index >= 0.5) return 'viability-medium-high';
    if (index >= 0.3) return 'viability-medium';
    return 'viability-low';
  }
}
