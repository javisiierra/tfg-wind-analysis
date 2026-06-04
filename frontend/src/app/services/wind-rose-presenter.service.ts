import { Injectable } from '@angular/core';
import { WindRoseDTO } from '../models/api-contracts';

export interface WindRoseSector {
  direction: string;
  percentage: number | null;
  meanSpeed: number | null;
  samples: number | null;
  velocity_range?: { min?: number; max?: number };
  raw: WindRoseDTO | null;
  angle: number;
  path: string;
  color: string;
}

@Injectable({
  providedIn: 'root'
})
export class WindRosePresenterService {
  readonly directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  readonly rings = [3, 6, 9, 12];

  private readonly center = 210;
  private readonly maxRadius = 150;
  private readonly innerRadius = 4;
  private readonly sectorDegrees = 360 / this.directions.length;
  private readonly palette = [
    '#0ea5e9', '#be4372', '#a76732', '#d6bd67',
    '#2e938c', '#6d49bd', '#8c929d', '#126898',
    '#be4372', '#a76732', '#a69355', '#31949a',
    '#6d49bd', '#8c929d', '#126898', '#be4372'
  ];

  buildWindRoseSectors(rawData: WindRoseDTO[]): WindRoseSector[] {
    console.debug('[Dashboard][WindRose] raw response', rawData);

    const dataByDirection = new Map<string, WindRoseDTO>();

    rawData.forEach((item) => {
      const direction = this.normalizeDirectionName(item?.direction);
      if (direction) {
        dataByDirection.set(direction, item);
      }
    });

    return this.directions.map((direction, index) => {
      const item = dataByDirection.get(direction);
      const percentage = item ? this.normalizePercentageScale(item.frequency) : null;
      const meanSpeed = item?.mean_speed ?? null;
      const samples = item?.sample_count ?? null;
      const angle = index * this.sectorDegrees;
      const radius = this.radiusForPercentage(percentage ?? 0);

      return {
        direction,
        percentage,
        meanSpeed,
        samples,
        velocity_range: item?.velocity_range,
        raw: item ?? null,
        angle,
        path: this.buildWindRoseSectorPath(angle, radius),
        color: this.palette[index % this.palette.length]
      };
    });
  }

  getDirectionLabel(degrees: number): string {
    const index = Math.round(degrees / 22.5) % 16;
    return this.directions[index];
  }

  normalizePercentageScale(value: number): number {
    return value >= 0 && value <= 1 ? Number((value * 100).toFixed(2)) : Number(value.toFixed(2));
  }

  normalizeDirectionName(direction: unknown): string | null {
    const value = String(direction ?? '').trim().toUpperCase();
    return this.directions.includes(value) ? value : null;
  }

  private buildWindRoseSectorPath(centerAngle: number, outerRadius: number): string {
    const startAngle = centerAngle - this.sectorDegrees / 2;
    const endAngle = centerAngle + this.sectorDegrees / 2;
    const innerStart = this.polarPoint(startAngle, this.innerRadius);
    const outerStart = this.polarPoint(startAngle, outerRadius);
    const outerEnd = this.polarPoint(endAngle, outerRadius);
    const innerEnd = this.polarPoint(endAngle, this.innerRadius);
    const largeArcFlag = this.sectorDegrees > 180 ? 1 : 0;

    return [
      `M ${innerStart.x} ${innerStart.y}`,
      `L ${outerStart.x} ${outerStart.y}`,
      `A ${outerRadius.toFixed(2)} ${outerRadius.toFixed(2)} 0 ${largeArcFlag} 1 ${outerEnd.x} ${outerEnd.y}`,
      `L ${innerEnd.x} ${innerEnd.y}`,
      `A ${this.innerRadius} ${this.innerRadius} 0 ${largeArcFlag} 0 ${innerStart.x} ${innerStart.y}`,
      'Z'
    ].join(' ');
  }

  private polarPoint(angleDegrees: number, radius: number): { x: string; y: string } {
    const radians = angleDegrees * Math.PI / 180;
    const x = this.center + radius * Math.sin(radians);
    const y = this.center - radius * Math.cos(radians);

    return {
      x: x.toFixed(2),
      y: y.toFixed(2)
    };
  }

  private radiusForPercentage(percentage: number): number {
    const maxRing = Math.max(...this.rings);
    const clamped = Math.max(0, Math.min(percentage, maxRing));
    return Math.max(this.innerRadius, (clamped / maxRing) * this.maxRadius);
  }
}
