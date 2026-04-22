import { Component, EventEmitter, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { CommonModule, JsonPipe } from '@angular/common';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [FormsModule, CommonModule, JsonPipe],
  templateUrl: './topbar.html',
  styleUrl: './topbar.css',
})
export class Topbar {
  casePath = '';

  @Output() caseChange = new EventEmitter<string>();

  result: any = null;
  error: any = null;
  loading = false;

  constructor(private http: HttpClient) {}

  runBase() {
    this.caseChange.emit(this.casePath);

    this.loading = true;
    this.result = null;
    this.error = null;

    this.http.post('http://127.0.0.1:8000/api/v1/pipeline/run-base', {
      case_path: this.casePath
    }).subscribe({
      next: (res) => {
        this.result = res;
        this.loading = false;
      },
      error: (err) => {
        this.error = err;
        this.loading = false;
      }
    });
  }

  get statusText(): string {
    if (this.loading) return '⏳ Ejecutando pipeline base...';
    if (this.error) return '❌ Error en la ejecución';
    if (this.result) return '✅ Pipeline base completado';
    return '';
  }
}