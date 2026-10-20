import {
  afterNextRender,
  Component,
  computed,
  ElementRef,
  inject,
  Injector,
  input,
  linkedSignal,
  model,
  signal,
} from '@angular/core';

/** An option of the list: what is kept (`value`) and what the person reads (`label`). */
export interface ComboOption {
  readonly value: string;
  readonly label: string;
}

/**
 * A box where a value can be typed or picked from a list of its own. Typing counts as soon as
 * `parse` reads it as one of the options; anything else leaves the box without a value. It
 * follows the combobox pattern of the WAI-ARIA practices with a list that does not filter: a
 * click or Alt+Down opens the list, Down and Up move through it (and open it), Enter picks the
 * highlighted option and Escape closes it. It starts empty when `value` is.
 *
 * ```html
 * <agl-combo-box inputId="hour" [options]="hours" [parse]="parseHour" [(value)]="hour"
 *   [ariaLabel]="t('hour')" />
 * ```
 */
@Component({
  selector: 'agl-combo-box',
  templateUrl: './combo-box.html',
  host: {
    class: 'relative block',
    '(document:pointerdown)': 'onDocumentPointerDown($event)',
    '(focusout)': 'onFocusOut($event)',
  },
})
export class ComboBox {
  /** The id of the box. */
  readonly inputId = input.required<string>();
  readonly options = input.required<readonly ComboOption[]>();
  /** The option a typed text means, or `null`; by default, the option with that exact label. */
  readonly parse = input<(text: string) => string | null>();
  /** The chosen option's value, or empty when there is none. */
  readonly value = model('');
  /** The accessible name of the box and its list, already translated. */
  readonly ariaLabel = input.required<string>();
  /** What the box says while it is empty. */
  readonly placeholder = input('');
  readonly inputMode = input<'numeric' | 'text'>('text');
  /** Whether the box shows as invalid (`aria-invalid`). */
  readonly invalid = input(false);
  /** The ids of the elements that describe the box, such as its error message. */
  readonly describedBy = input<string>();
  /** The `data-testid` of the box, for the end-to-end tests. */
  readonly testId = input<string>();

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);

  protected readonly open = signal(false);
  /**
   * What the box shows: what the person is typing while it means the chosen value (so `1` is not
   * rewritten as `01` before the `2` of `12`), or the chosen option's label.
   */
  protected readonly text = linkedSignal<string, string>({
    source: this.value,
    computation: (value, previous) =>
      previous !== undefined && (this.read(previous.value) ?? '') === value
        ? previous.value
        : this.labelOf(value),
  });
  /** The option the keyboard is on while the list is open. */
  protected readonly activeValue = signal('');

  protected readonly listId = computed(() => `${this.inputId()}-options`);

  protected optionId(value: string): string {
    return `${this.inputId()}-option-${value}`;
  }

  protected onClick(): void {
    if (!this.open()) {
      this.show();
    }
  }

  protected toggle(): void {
    if (this.open()) {
      this.close(true);
    } else {
      this.show();
      this.box()?.focus();
    }
  }

  protected onInput(text: string): void {
    this.text.set(text);
    const parsed = this.read(text);
    this.value.set(parsed ?? '');
    if (this.open() && parsed !== null) {
      this.moveTo(parsed);
    }
  }

  protected onKeydown(event: KeyboardEvent): void {
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowUp':
        event.preventDefault();
        if (!this.open()) {
          this.show();
        } else if (!event.altKey) {
          this.moveBy(event.key === 'ArrowDown' ? 1 : -1);
        }
        return;
      case 'Enter':
        if (this.open()) {
          event.preventDefault();
          this.pick(this.activeValue());
        }
        return;
      case 'Escape':
        if (this.open()) {
          event.preventDefault();
          this.close(true);
        }
        return;
    }
  }

  protected pick(value: string): void {
    this.value.set(value);
    this.text.set(this.labelOf(value));
    this.close(true);
  }

  /** Leaving the box drops what was typed if it was not an option. */
  protected onBoxBlur(): void {
    if (!this.open()) {
      this.text.set(this.labelOf(this.value()));
    }
  }

  protected onDocumentPointerDown(event: PointerEvent): void {
    if (this.open() && !this.contains(event.target)) {
      this.close(false);
    }
  }

  protected onFocusOut(event: FocusEvent): void {
    if (this.open() && event.relatedTarget !== null && !this.contains(event.relatedTarget)) {
      this.close(false);
    }
  }

  /** Opens the list on the chosen option or, with none, on the first one. */
  private show(): void {
    this.open.set(true);
    this.moveTo(this.value() !== '' ? this.value() : (this.options()[0]?.value ?? ''));
  }

  private moveBy(steps: number): void {
    const options = this.options();
    const index = options.findIndex((option) => option.value === this.activeValue());
    const next = options[(index + steps + options.length) % options.length];
    if (next !== undefined) {
      this.moveTo(next.value);
    }
  }

  private moveTo(value: string): void {
    this.activeValue.set(value);
    afterNextRender(
      () => {
        this.host.nativeElement
          .querySelector(`#${this.optionId(value)}`)
          ?.scrollIntoView({ block: 'nearest' });
      },
      { injector: this.injector },
    );
  }

  /** Closes the list; the box keeps the chosen option and, unless it went elsewhere, the focus. */
  private close(returnFocus: boolean): void {
    this.open.set(false);
    this.text.set(this.labelOf(this.value()));
    if (returnFocus) {
      this.box()?.focus();
    }
  }

  private read(text: string): string | null {
    const parse = this.parse();
    if (parse !== undefined) {
      return parse(text);
    }
    return this.options().find((option) => option.label === text.trim())?.value ?? null;
  }

  private labelOf(value: string): string {
    return this.options().find((option) => option.value === value)?.label ?? '';
  }

  private box(): HTMLInputElement | null {
    return this.host.nativeElement.querySelector<HTMLInputElement>(`#${this.inputId()}`);
  }

  private contains(target: EventTarget | null): boolean {
    return target instanceof Node && this.host.nativeElement.contains(target);
  }
}
