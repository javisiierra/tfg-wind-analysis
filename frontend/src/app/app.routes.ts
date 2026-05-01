import { Routes } from '@angular/router';
import { HomeComponent } from './components/home/home';
import { MapWrapperComponent } from './components/map-wrapper/map-wrapper';
import { DashboardComponent } from './components/dashboard/dashboard';
import { AppLayoutComponent } from './components/app-layout/app-layout';

export const routes: Routes = [
  { path: '', component: HomeComponent },
  {
    path: '',
    component: AppLayoutComponent,
    children: [
      { path: 'mapa', component: MapWrapperComponent },
      { path: 'dashboard', component: DashboardComponent }
    ]
  },
  { path: '**', redirectTo: '' }
];
