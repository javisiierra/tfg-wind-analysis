import { Component, EventEmitter, Input, Output } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule, JsonPipe } from '@angular/common';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, JsonPipe],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css'
})
export class Sidebar {
  @Input() casePath: string = '';
  @Output() layerSelected = new EventEmitter<string>();

  result: any = null;
  error: any = null;
  loading = false;
  currentAction = '';

  constructor(private http: HttpClient) {}

  runWindNinja() {
    this.call('/run-windninja', 'WindNinja');
  }

  runRename() {
    this.call('/run-rename', 'Rename');
  }

  runWindRose() {
    this.call('/run-wind-rose', 'Wind Rose');
  }

  showApoyos() {
    this.layerSelected.emit('apoyos');
  }

  showVanos() {
    this.layerSelected.emit('vanos');
  }

  showDominio() {
    this.layerSelected.emit('dominio');
  }

  private call(endpoint: string, action: string) {
    this.loading = true;
    this.result = null;
    this.error = null;
    this.currentAction = action;

    this.http.post(`http://127.0.0.1:8000/api/v1/pipeline${endpoint}`, {
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
}