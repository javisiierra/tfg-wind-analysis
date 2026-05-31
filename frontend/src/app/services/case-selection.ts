import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

interface AllowedCase {
  name: string;
  case_path: string;
}

interface AllowedCasesResponse {
  cases: AllowedCase[];
}

export async function selectAllowedCasePath(http: HttpClient, apiUrl: string): Promise<string | null> {
  const response = await firstValueFrom(http.get<AllowedCasesResponse>(`${apiUrl}/case/list`));
  const cases = response.cases ?? [];

  if (cases.length === 0) {
    throw new Error('No hay carpetas de casos disponibles dentro de HOST_CASES_ROOT.');
  }

  const options = cases.map((item, index) => `${index + 1}. ${item.name}`).join('\n');
  const selection = window.prompt(`Selecciona un caso permitido:\n${options}`);

  if (selection === null) {
    return null;
  }

  const selectedIndex = Number(selection.trim()) - 1;
  if (!Number.isInteger(selectedIndex) || selectedIndex < 0 || selectedIndex >= cases.length) {
    throw new Error('La selección no corresponde a una carpeta permitida.');
  }

  return cases[selectedIndex].case_path;
}
