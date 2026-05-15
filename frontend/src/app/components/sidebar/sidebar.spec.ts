import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { Sidebar } from './sidebar';

describe('Sidebar', () => {
  let component: Sidebar;
  let fixture: ComponentFixture<Sidebar>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Sidebar],
      providers: [provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();

    fixture = TestBed.createComponent(Sidebar);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
  });

  afterEach(() => httpMock.verify());

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should emit refresh status requests', () => {
    const spy = vi.fn();
    component.refreshStatusRequested.subscribe(spy);
    component.onRefreshStatusClick();
    expect(spy).toHaveBeenCalledOnce();
  });

  it('should emit draw mode changes', () => {
    const spy = vi.fn();
    component.drawModeChange.subscribe(spy);
    component.startSupportDraw();
    component.finishSupportDraw();
    expect(spy).toHaveBeenCalledWith('support');
    expect(spy).toHaveBeenCalledWith('none');
  });

  it('saveCase should validate geometries before calling api', async () => {
    component.caseName = 'case1';
    component.drawnGeometries = [];
    await component.saveCase();
    expect(component.error?.message).toContain('dibujar');
  });

  it('runWindNinja should show complete postprocess message and refresh status', () => {
    const completedSpy = vi.fn();
    component.casePath = 'C:/case';
    component.caseStatus = { ready_for_windninja: true } as any;
    component.actionCompletedOk.subscribe(completedSpy);

    component.runWindNinja();

    const req = httpMock.expectOne('http://127.0.0.1:8000/api/v1/pipeline/run-windninja');
    req.flush({
      status: 'ok',
      rename_success: true,
      worst_supports_success: true,
      postprocess_warnings: []
    });

    expect(component.userMessage).toBe('WindNinja finalizado. Salidas renombradas y vanos críticos calculados.');
    expect(completedSpy).toHaveBeenCalledWith('C:/case');
  });

  it('runWindNinja should show postprocess warning message', () => {
    component.casePath = 'C:/case';
    component.caseStatus = { ready_for_windninja: true } as any;

    component.runWindNinja();

    const req = httpMock.expectOne('http://127.0.0.1:8000/api/v1/pipeline/run-windninja');
    req.flush({
      status: 'ok',
      rename_success: true,
      worst_supports_success: false,
      worst_supports_warning: 'analysis failed',
      postprocess_warnings: ['analysis failed']
    });

    expect(component.userMessage).toBe('WindNinja finalizado, pero hubo avisos en el postproceso.');
  });
});
