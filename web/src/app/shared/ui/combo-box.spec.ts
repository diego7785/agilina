import { Component, signal } from '@angular/core';
import { TestBed, type ComponentFixture } from '@angular/core/testing';

import { ComboBox, type ComboOption } from './combo-box';

const OPTIONS: readonly ComboOption[] = ['01', '02', '03', '12'].map((value) => ({
  value,
  label: value,
}));

@Component({
  imports: [ComboBox],
  template: `
    <agl-combo-box
      inputId="hour"
      testId="hour-box"
      describedBy="hour-problem"
      placeholder="--"
      ariaLabel="Hora"
      inputMode="numeric"
      [options]="options"
      [parse]="parse"
      [invalid]="invalid()"
      [(value)]="value"
    />
    <p id="hour-problem">Elige la hora.</p>
    <button type="button" id="elsewhere">Otro</button>
  `,
})
class Host {
  readonly options = OPTIONS;
  readonly value = signal('02');
  readonly invalid = signal(false);
  readonly parse = (text: string): string | null =>
    OPTIONS.find((option) => Number(option.value) === Number(text) && text.trim() !== '')?.value ??
    null;
}

describe('ComboBox', () => {
  let fixture: ComponentFixture<Host>;
  let host: Host;
  let root: HTMLElement;

  beforeEach(async () => {
    fixture = TestBed.createComponent(Host);
    host = fixture.componentInstance;
    root = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
  });

  function box(): HTMLInputElement {
    return root.querySelector<HTMLInputElement>('#hour')!;
  }

  function list(): HTMLElement {
    return root.querySelector<HTMLElement>('[role="listbox"]')!;
  }

  function option(value: string): HTMLElement | null {
    return root.querySelector<HTMLElement>(`#hour-option-${value}`);
  }

  function active(): string {
    const id = box().getAttribute('aria-activedescendant');
    return id === null ? '' : (root.querySelector(`#${id}`)?.textContent.trim() ?? '');
  }

  async function open(): Promise<void> {
    box().click();
    await fixture.whenStable();
  }

  async function type(text: string): Promise<void> {
    box().value = text;
    box().dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  async function press(key: string): Promise<void> {
    box().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    await fixture.whenStable();
  }

  it('is a named combobox that shows the chosen option', async () => {
    host.invalid.set(true);
    await fixture.whenStable();

    expect(box().getAttribute('role')).toBe('combobox');
    expect(box().getAttribute('aria-label')).toBe('Hora');
    expect(box().getAttribute('inputmode')).toBe('numeric');
    expect(box().getAttribute('aria-describedby')).toBe('hour-problem');
    expect(box().getAttribute('aria-invalid')).toBe('true');
    expect(box().getAttribute('data-testid')).toBe('hour-box');
    expect(box().value).toBe('02');
    expect(list().hidden).toBeTrue();
  });

  it('starts empty, with its placeholder, when nothing is chosen', async () => {
    host.value.set('');
    await fixture.whenStable();

    expect(box().value).toBe('');
    expect(box().placeholder).toBe('--');
  });

  it('opens its list on the chosen option', async () => {
    await open();

    expect(box().getAttribute('aria-expanded')).toBe('true');
    expect(list().getAttribute('aria-label')).toBe('Hora');
    expect(root.querySelectorAll('[role="option"]').length).toBe(4);
    expect(active()).toBe('02');
    expect(option('02')!.getAttribute('aria-selected')).toBe('true');
  });

  it('opens on the first option when nothing is chosen', async () => {
    host.value.set('');
    await fixture.whenStable();

    await open();

    expect(active()).toBe('01');
    expect(root.querySelector('[aria-selected="true"]')).toBeNull();
  });

  it('picks an option with the pointer, closes and keeps the focus on the box', async () => {
    await open();

    option('12')!.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    await fixture.whenStable();

    expect(host.value()).toBe('12');
    expect(box().value).toBe('12');
    expect(list().hidden).toBeTrue();
    expect(document.activeElement).toBe(box());
  });

  it('moves with the arrows, going around the ends, and picks with Enter', async () => {
    box().focus();
    await press('ArrowDown');
    expect(list().hidden).toBeFalse();

    await press('ArrowUp');
    await press('ArrowUp');
    expect(active()).toBe('12');
    await press('ArrowDown');
    expect(active()).toBe('01');

    await press('Enter');
    expect(host.value()).toBe('01');
    expect(list().hidden).toBeTrue();
  });

  it('closes with Escape without changing the value', async () => {
    await open();
    await press('ArrowDown');

    await press('Escape');

    expect(list().hidden).toBeTrue();
    expect(host.value()).toBe('02');
  });

  it('takes what is typed as soon as it means an option, without rewriting it', async () => {
    await type('1');
    expect(host.value()).toBe('01');
    expect(box().value).toBe('1');

    await type('12');
    expect(host.value()).toBe('12');
  });

  it('has no value while what is typed is not an option, and drops it on leaving', async () => {
    await type('7');
    expect(host.value()).toBe('');

    box().dispatchEvent(new Event('blur'));
    await fixture.whenStable();

    expect(box().value).toBe('');
  });

  it('shows the option of the label once the person leaves the box', async () => {
    await type('3');

    box().dispatchEvent(new Event('blur'));
    await fixture.whenStable();

    expect(box().value).toBe('03');
  });

  it('follows what is typed in the open list', async () => {
    await open();

    await type('12');

    expect(active()).toBe('12');
  });

  it('closes when the person clicks elsewhere or moves the focus out', async () => {
    await open();
    document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    await fixture.whenStable();
    expect(list().hidden).toBeTrue();

    await open();
    root.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    box().dispatchEvent(
      new FocusEvent('focusout', {
        bubbles: true,
        relatedTarget: root.querySelector('#elsewhere'),
      }),
    );
    await fixture.whenStable();
    expect(list().hidden).toBeTrue();
  });

  it('opens and closes with its arrow button', async () => {
    const button = root.querySelector<HTMLButtonElement>('button[aria-hidden="true"]')!;

    button.click();
    await fixture.whenStable();
    expect(list().hidden).toBeFalse();

    button.click();
    await fixture.whenStable();
    expect(list().hidden).toBeTrue();
  });
});

@Component({
  imports: [ComboBox],
  template: `<agl-combo-box
    inputId="mode"
    ariaLabel="Modo"
    [options]="options"
    [(value)]="value"
  />`,
})
class PlainHost {
  readonly options: readonly ComboOption[] = [
    { value: 'support', label: 'Soporte' },
    { value: 'autonomous', label: 'Autónomo' },
  ];
  readonly value = signal('');
}

describe('ComboBox without a parser', () => {
  it('takes a typed text that is exactly the label of an option', async () => {
    const fixture = TestBed.createComponent(PlainHost);
    await fixture.whenStable();
    const box = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>('#mode')!;

    box.value = 'Soporte';
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();

    expect(fixture.componentInstance.value()).toBe('support');
  });
});
