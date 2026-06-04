import { Injectable } from '@angular/core';
import { DashboardJobStatus } from '../models/api-contracts';

@Injectable({
  providedIn: 'root'
})
export class DashboardJobStateService {
  initializeYears(currentYear = new Date().getFullYear(), yearsBack = 10): number[] {
    const years: number[] = [];

    for (let i = currentYear; i >= currentYear - yearsBack; i--) {
      years.push(i);
    }

    return years;
  }

  buildEtaMessage(
    progress: number,
    status: DashboardJobStatus,
    progressMessage: string,
    analysisStartedAtMs: number | null,
    nowMs = Date.now()
  ): string {
    if (!analysisStartedAtMs || status === 'finished') {
      return '';
    }

    const elapsedMs = nowMs - analysisStartedAtMs;

    if (progress <= 0 || elapsedMs < 1000) {
      return 'Backend activo. Calculando tiempo estimado...';
    }

    const elapsedText = this.formatDuration(elapsedMs);
    const normalizedProgress = Math.max(5, Math.min(progress, 95));
    const progressBasedRemainingMs = elapsedMs * ((100 - normalizedProgress) / normalizedProgress);
    const message = String(progressMessage ?? '').toLowerCase();

    if (progress >= 75 && progress < 90) {
      return `Backend activo. Tiempo transcurrido: ${elapsedText}. Esperando a Copernicus/ERA5; esta fase puede tardar 5-10 min.`;
    }

    if (progress >= 90) {
      return `Backend activo. Tiempo transcurrido: ${elapsedText}. Ultimos calculos, queda poco.`;
    }

    const nominalTotalMs = message.includes('cache') ? 120000 : 600000;
    const nominalRemainingMs = Math.max(0, nominalTotalMs - elapsedMs);
    const remainingMs = Math.max(progressBasedRemainingMs, nominalRemainingMs);

    return `Backend activo. Transcurrido: ${elapsedText}. Estimado restante: ${this.formatDuration(remainingMs)} aprox.`;
  }

  formatDuration(durationMs: number): string {
    const totalSeconds = Math.max(1, Math.round(durationMs / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    if (minutes <= 0) {
      return `${seconds} s`;
    }

    if (seconds === 0) {
      return `${minutes} min`;
    }

    return `${minutes} min ${seconds} s`;
  }

  isDomainMissingError(message: string): boolean {
    const text = String(message ?? '').toLowerCase();

    return (
      text.includes('no existe dominio') ||
      text.includes('no tiene dominio') ||
      text.includes('falta dominio') ||
      text.includes('invalid_case_domain') ||
      text.includes('dominio.geojson') ||
      text.includes('dominio.shp') ||
      text.includes('genera el dominio')
    );
  }
}
