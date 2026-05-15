import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MapComponent } from './map';

describe('MapComponent', () => {
  let component: MapComponent;
  let fixture: ComponentFixture<MapComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MapComponent],
    }).compileComponents();

    fixture = TestBed.createComponent(MapComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should not fail when unsupported layer is requested', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    component['loadLayerIntoSource']('invalid', '/tmp', undefined, true);
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });
});
