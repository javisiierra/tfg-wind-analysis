import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { Topbar } from './topbar';
import { environment } from '../../../environments/environment';

describe('Topbar', () => {
  let component: Topbar;
  let fixture: ComponentFixture<Topbar>;
  let httpMock: HttpTestingController;

  const apiUrl = environment.apiUrl;

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

    const req = httpMock.expectOne(`${apiUrl}/case/import-folder`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ input_path: '/data/case-a' });
    req.flush({ status: 'ready', case_path: '/data/case-a' });

    expect(completedSpy).toHaveBeenCalledWith('/data/case-a');
  });

  it('Ejecutar preparación should call modern preparation then WindNinja', async () => {
    const completedSpy = vi.fn();
    component.casePath = '/data/case-ready-inputs';
    component.preparationCompleted.subscribe(completedSpy);

    const promise = component.executePreparationPipeline();

    flushRequest(`${apiUrl}/pipeline/run-preparation`, {
      status: 'ok',
      case_path: component.casePath,
      domain: { generated: false },
      dem: { out_mdt_tif: '/data/case-ready-inputs/MDT_WN/mdt.tif' },
      weather: { station_files: [] }
    });
    await tickPromises();

    httpMock.expectNone(`${apiUrl}/case/status`);
    httpMock.expectNone(`${apiUrl}/domain/generate-from-supports`);
    httpMock.expectNone(`${apiUrl}/vanos/generate-from-supports`);
    httpMock.expectNone(`${apiUrl}/domain/generate-dem`);
    httpMock.expectNone(`${apiUrl}/domain/generate-weather`);

    flushRequest(`${apiUrl}/pipeline/run-windninja`, {
      status: 'ok',
      windninja_success: true,
      rename_success: true,
      wind_rose_success: true
    });
    await promise;

    expect(completedSpy).toHaveBeenCalledWith('/data/case-ready-inputs');
  });

  it('Ejecutar preparación should expose WindNinja result', async () => {
    component.casePath = '/data/case-needs-inputs';

    const promise = component.executePreparationPipeline();

    flushRequest(`${apiUrl}/pipeline/run-preparation`, {
      status: 'ok',
      case_path: component.casePath,
      domain: { generated: true },
      vanos: { status: 'generated' },
      dem: { out_mdt_tif: '/data/case-needs-inputs/MDT_WN/mdt.tif' },
      weather: { station_files: [] }
    });
    await tickPromises();

    flushRequest(`${apiUrl}/pipeline/run-windninja`, { status: 'ok', windninja_success: true });
    await promise;

    expect(component.result?.['windninja_success']).toBe(true);
  });

  it('Ejecutar preparación should stop and emit error when preparation fails', async () => {
    const stateSpy = vi.fn();
    component.casePath = '/data/case-error';
    component.executionUiStateChange.subscribe(stateSpy);

    const promise = component.executePreparationPipeline();

    const preparationReq = httpMock.expectOne(`${apiUrl}/pipeline/run-preparation`);
    preparationReq.flush({ detail: 'DEM failed' }, { status: 500, statusText: 'Server Error' });
    await promise;

    httpMock.expectNone(`${apiUrl}/domain/generate-dem`);
    httpMock.expectNone(`${apiUrl}/domain/generate-weather`);
    httpMock.expectNone(`${apiUrl}/pipeline/run-windninja`);
    expect(stateSpy).toHaveBeenLastCalledWith({
      status: 'error',
      title: 'Error',
      stage: 'Preparando dominio, DEM y meteorologia',
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
