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

  it('should hide manual postprocess and refresh buttons from the main flow', () => {
    const text = fixture.nativeElement.textContent;
    expect(text).not.toContain('Run Rename');
    expect(text).not.toContain('Run Wind Rose');
    expect(text).not.toContain('Calcular 4');
    expect(text).not.toContain('Refrescar estado');
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
      wind_rose_success: true,
      postprocess_warnings: []
    });

    expect(component.userMessage).toBe('WindNinja finalizado. Salidas renombradas, vanos críticos y rosa de vientos generados.');
    expect(completedSpy).toHaveBeenCalledWith('C:/case');
  });

  it('runWindNinja should show wind rose warning message', () => {
    component.casePath = 'C:/case';
    component.caseStatus = { ready_for_windninja: true } as any;

    component.runWindNinja();

    const req = httpMock.expectOne('http://127.0.0.1:8000/api/v1/pipeline/run-windninja');
    req.flush({
      status: 'ok',
      rename_success: true,
      worst_supports_success: true,
      wind_rose_success: false,
      wind_rose_warning: 'rose failed',
      postprocess_warnings: ['rose failed']
    });

    expect(component.userMessage).toBe('WindNinja finalizado, pero no se pudo generar la rosa de vientos.');
  });
});
