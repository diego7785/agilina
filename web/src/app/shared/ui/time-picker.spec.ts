import { Component, signal } from '@angular/core';
import { TestBed, type ComponentFixture } from '@angular/core/testing';

import { TimePicker } from './time-picker';

@Component({
  imports: [TimePicker],
  template: `
    <label for="daily">Hora de la reunión</label>
    <agl-time-picker
      inputId="daily"
      testId="daily-time"
      describedBy="daily-problem"
      hourLabel="Hora"
      minuteLabel="Minutos"
      periodLabel="a. m. o p. m."
      amLabel="a. m."
      pmLabel="p. m."
      [invalid]="invalid()"
      [(value)]="value"
      (touched)="touches.set(touches() + 1)"
    />
    <p id="daily-problem">Elige la hora.</p>
    <button type="button" id="elsewhere">Otro</button>
  `,
})
class Host {
  readonly value = signal('');
  readonly invalid = signal(false);
  readonly touches = signal(0);
}

describe('TimePicker', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;
  let root: HTMLElement;

  beforeEach(async () => {
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    root = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  });

  function boxes(): HTMLInputElement[] {
    return ['#daily', '#daily-minute', '#daily-period'].map((id) =>
      root.querySelector<HTMLInputElement>(id)!,
    );
  }

  function shown(): string[] {
    return boxes().map((box) => box.value);
  }

  async function type(index: number, text: string): Promise<void> {
    const box = boxes()[index]!;
    box.value = text;
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  async function show(value: string): Promise<void> {
    host.value.set(value);
    await fixture.whenStable();
  }

  it('is a group of three named boxes, the hour tied to the label, all empty at first', () => {
    const [hour, minute, period] = boxes();

    expect(root.querySelector('agl-time-picker')!.getAttribute('role')).toBe('group');
    expect(root.querySelector('label')!.htmlFor).toBe(hour!.id);
    expect(boxes().map((box) => box.getAttribute('aria-label'))).toEqual([
      'Hora',
      'Minutos',
      'a. m. o p. m.',
    ]);
    expect(shown()).toEqual(['', '', '']);
    expect(hour!.getAttribute('data-testid')).toBe('daily-time');
    expect(minute!.getAttribute('data-testid')).toBe('daily-time-minute');
    expect(period!.getAttribute('data-testid')).toBe('daily-time-period');
  });

  it('describes every box with the error and marks them all invalid', async () => {
    host.invalid.set(true);
    await fixture.whenStable();

    for (const box of boxes()) {
      expect(box.getAttribute('aria-describedby')).toBe('daily-problem');
      expect(box.getAttribute('aria-invalid')).toBe('true');
    }
  });

  it('offers the twelve hours, every minute and a. m. or p. m.', async () => {
    const counts: number[] = [];
    for (const box of boxes()) {
      box.click();
      await fixture.whenStable();
      counts.push(root.querySelectorAll('[role="option"]').length);
      box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await fixture.whenStable();
    }

    expect(counts).toEqual([12, 60, 2]);
  });

  it('shows a saved time in its three parts, in twelve hours', async () => {
    await show('14:05');
    expect(shown()).toEqual(['02', '05', 'p. m.']);

    await show('00:30');
    expect(shown()).toEqual(['12', '30', 'a. m.']);

    await show('12:00');
    expect(shown()).toEqual(['12', '00', 'p. m.']);
  });

  it('holds no time until the three parts are chosen, then the time in 24 hours', async () => {
    await type(0, '9');
    await type(1, '7');
    expect(host.value()).toBe('');

    await type(2, 'p');
    expect(host.value()).toBe('21:07');
  });

  it('reads a. m. and p. m. from what starts with an a or a p', async () => {
    await type(0, '12');
    await type(1, '00');

    await type(2, 'AM');
    expect(host.value()).toBe('00:00');
    await type(2, 'p. m.');
    expect(host.value()).toBe('12:00');
    await type(2, 'x');
    expect(host.value()).toBe('');
  });

  it('rejects an hour out of 1 to 12 and minutes out of 00 to 59', async () => {
    await show('09:30');

    await type(0, '13');
    expect(host.value()).toBe('');
    await type(0, '9');
    await type(1, '60');
    expect(host.value()).toBe('');
  });

  it('keeps the other parts when one is cleared', async () => {
    await show('09:30');

    await type(0, '');
    expect(host.value()).toBe('');
    expect(shown()).toEqual(['', '30', 'a. m.']);

    await type(0, '10');
    expect(host.value()).toBe('10:30');
  });

  it('counts as touched only when the focus leaves the three boxes', () => {
    const [hour, minute] = boxes();

    hour!.dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: minute! }));
    expect(host.touches()).toBe(0);

    minute!.dispatchEvent(
      new FocusEvent('focusout', {
        bubbles: true,
        relatedTarget: root.querySelector('#elsewhere'),
      }),
    );
    expect(host.touches()).toBe(1);
  });
});
