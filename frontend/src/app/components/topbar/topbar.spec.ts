import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { Topbar } from './topbar';

describe('Topbar', () => {
  let component: Topbar;
  let fixture: ComponentFixture<Topbar>;
  let httpMock: HttpTestingController;

  const apiBaseUrl = 'http://localhost:8000/api/v1';

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Topbar],
      providers: [provideHttpClient(), provideHttpClientTesting()]
    }).compileComponents();

    fixture = TestBed.createComponent(Topbar);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should render import and preparation actions', () => {
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;

    expect(text).toContain('Importar carpeta');
    expect(text).toContain('Ejecutar preparación');
    expect(text).not.toContain('Preparar caso');
  });

  it('Importar carpeta should keep calling /case/import-folder', () => {
    const completedSpy = vi.fn();
    component.casePath = '/data/case-a';
    component.casePrepared.subscribe(completedSpy);

    component.prepareCase();

    const req = httpMock.expectOne(`${apiBaseUrl}/case/import-folder`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ input_path: '/data/case-a' });
    req.flush({ status: 'ready', case_path: '/data/case-a' });

    expect(completedSpy).toHaveBeenCalledWith('/data/case-a');
  });

  it('Ejecutar preparación should skip existing domain and vanos', async () => {
    const completedSpy = vi.fn();
    component.casePath = '/data/case-ready-inputs';
    component.preparationCompleted.subscribe(completedSpy);

    const promise = component.executePreparationPipeline();

    flushRequest(`${apiBaseUrl}/case/status`, {
      status: 'ok',
      case_path: component.casePath,
      has_domain: true,
      has_vanos: true,
      has_dem: false,
      has_weather: false,
      has_apoyos: true,
      ready_for_windninja: false
    });
    await tickPromises();

    httpMock.expectNone(`${apiBaseUrl}/domain/generate-from-supports`);
    httpMock.expectNone(`${apiBaseUrl}/vanos/generate-from-supports`);

    flushRequest(`${apiBaseUrl}/domain/generate-dem`, { status: 'ok' });
    await tickPromises();

    flushRequest(`${apiBaseUrl}/domain/generate-weather`, { status: 'ok' });
    await tickPromises();

    flushRequest(`${apiBaseUrl}/pipeline/run-windninja`, {
      status: 'ok',
      windninja_success: true,
      rename_success: true,
      wind_rose_success: true
    });
    await promise;

    expect(completedSpy).toHaveBeenCalledWith('/data/case-ready-inputs');
  });

  it('Ejecutar preparación should run domain, vanos, DEM, weather and WindNinja in order', async () => {
    component.casePath = '/data/case-needs-inputs';

    const promise = component.executePreparationPipeline();

    flushRequest(`${apiBaseUrl}/case/status`, {
      status: 'ok',
      case_path: component.casePath,
      has_domain: false,
      has_vanos: false,
      has_dem: false,
      has_weather: false,
      has_apoyos: true,
      ready_for_windninja: false
    });
    await tickPromises();

    flushRequest(`${apiBaseUrl}/domain/generate-from-supports`, { status: 'ok' });
    await tickPromises();

    flushRequest(`${apiBaseUrl}/case/status`, {
      status: 'ok',
      case_path: component.casePath,
      has_domain: true,
      has_vanos: false,
      has_dem: false,
      has_weather: false,
      has_apoyos: true,
      ready_for_windninja: false
    });
    await tickPromises();

    flushRequest(`${apiBaseUrl}/vanos/generate-from-supports`, { status: 'ok' });
    await tickPromises();

    flushRequest(`${apiBaseUrl}/domain/generate-dem`, { status: 'ok' });
    await tickPromises();

    flushRequest(`${apiBaseUrl}/domain/generate-weather`, { status: 'ok' });
    await tickPromises();

    flushRequest(`${apiBaseUrl}/pipeline/run-windninja`, { status: 'ok', windninja_success: true });
    await promise;

    expect(component.result?.['windninja_success']).toBe(true);
  });

  it('Ejecutar preparación should stop and emit error when a stage fails', async () => {
    const stateSpy = vi.fn();
    component.casePath = '/data/case-error';
    component.executionUiStateChange.subscribe(stateSpy);

    const promise = component.executePreparationPipeline();

    flushRequest(`${apiBaseUrl}/case/status`, {
      status: 'ok',
      case_path: component.casePath,
      has_domain: true,
      has_vanos: true,
      has_dem: false,
      has_weather: false,
      has_apoyos: true,
      ready_for_windninja: false
    });
    await tickPromises();

    const demReq = httpMock.expectOne(`${apiBaseUrl}/domain/generate-dem`);
    demReq.flush({ detail: 'DEM failed' }, { status: 500, statusText: 'Server Error' });
    await promise;

    httpMock.expectNone(`${apiBaseUrl}/domain/generate-weather`);
    httpMock.expectNone(`${apiBaseUrl}/pipeline/run-windninja`);
    expect(stateSpy).toHaveBeenLastCalledWith({
      status: 'error',
      title: 'Error',
      stage: 'Generando DEM',
      detail: 'DEM failed'
    });
  });

  function flushRequest(url: string, response: object): void {
    const req = httpMock.expectOne(url);
    expect(req.request.method).toBe('POST');
    req.flush(response);
  }

  async function tickPromises(): Promise<void> {
    await new Promise(resolve => setTimeout(resolve, 0));
  }
});
