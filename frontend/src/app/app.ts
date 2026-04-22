import { Component } from '@angular/core';
import { Topbar } from './components/topbar/topbar';
import { Sidebar } from './components/sidebar/sidebar';
import { MapComponent } from './components/map/map';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [Topbar, Sidebar, MapComponent],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  casePath = '';
  selectedLayer = '';
}
