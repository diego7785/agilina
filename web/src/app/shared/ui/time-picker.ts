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
  output,
  signal,
} from '@angular/core';

/** Minutes between two times of the list; any other time can still be typed. */
const STEP_MINUTES = 15;
const MINUTES_IN_A_DAY = 24 * 60;

/** Every time of the list, `HH:MM`, from 00:00 every `STEP_MINUTES`. */
const TIMES: readonly string[] = [...Array(MINUTES_IN_A_DAY / STEP_MINUTES).keys()].map((index) =>
  clockTime(index * STEP_MINUTES),
);
const MIDNIGHT = '00:00';

/**
 * A time box (`HH:MM`, 24 hours) where the time can be typed or picked from a list of its own,
 * instead of the browser's, which Safari does not have. Its label is a `<label for="…">`
 * pointing at `inputId`, the box itself:
 *
 * ```html
 * <label for="daily-time">Hora</label>
 * <agl-time-picker inputId="daily-time" [(value)]="dailyTime"
 *   [placeholder]="t('choose_time')" [listLabel]="t('times')" />
 * ```
 *
 * It follows the combobox pattern of the WAI-ARIA practices with a list that does not filter:
 * the box opens the list on click or with Alt+Down; Down and Up move through the times (and open
 * it), Enter picks the highlighted one and Escape closes it. What is typed counts as soon as it
 * is a time (`9:30`, `09:30` or `0930`); anything else leaves the box without a time, so the
 * form asks for one. Starts empty when `value` is: nothing is preselected.
 */
@Component({
  selector: 'agl-time-picker',
  templateUrl: './time-picker.html',
  host: {
    class: 'relative block',
    '(document:pointerdown)': 'onDocumentPointerDown($event)',
    '(focusout)': 'onFocusOut($event)',
  },
})
export class TimePicker {
  /** The id of the box, which its `<label for>` points at. */
  readonly inputId = input.required<string>();
  /** The chosen time, `HH:MM`, or empty when there is none. */
  readonly value = model('');
  /** What the box says while no time is written, already translated. */
  readonly placeholder = input.required<string>();
  /** The accessible name of the list of times, already translated. */
  readonly listLabel = input.required<string>();
  /** Whether the box shows as invalid (`aria-invalid`). */
  readonly invalid = input(false);
  /** The ids of the elements that describe the box, such as its error message. */
  readonly describedBy = input<string>();
  /** The `data-testid` of the box, for the end-to-end tests. */
  readonly testId = input<string>();
  /** The person left the box, after opening the list or not. */
  readonly touched = output();

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);

  protected readonly times = TIMES;
  protected readonly open = signal(false);
  /** What the box shows: the chosen time, or what the person is typing. */
  protected readonly text = linkedSignal(() => this.value());
  /** The time of the list the keyboard is on while it is open. */
  protected readonly activeTime = signal(MIDNIGHT);

  protected readonly listId = computed(() => `${this.inputId()}-times`);

  protected optionId(time: string): string {
    return `${this.inputId()}-time-${time.replace(':', '')}`;
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
    this.value.set(parseTime(text) ?? '');
    const typed = this.value();
    if (this.open() && typed !== '') {
      this.moveTo(nearestListedTime(typed));
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
          this.pick(this.activeTime());
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

  protected pick(time: string): void {
    this.value.set(time);
    this.text.set(time);
    this.close(true);
  }

  /** Leaving the box with the list closed counts as having been there. */
  protected onBoxBlur(): void {
    if (!this.open()) {
      this.text.set(this.value());
      this.touched.emit();
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

  /** Opens the list on the chosen time or, with none, on the next one of the clock. */
  private show(): void {
    const from = this.value() !== '' ? this.value() : clockTime(minutesOfDay(new Date()));
    this.open.set(true);
    this.moveTo(nearestListedTime(from));
  }

  private moveBy(steps: number): void {
    const index = TIMES.indexOf(this.activeTime());
    this.moveTo(TIMES[(index + steps + TIMES.length) % TIMES.length] ?? MIDNIGHT);
  }

  private moveTo(time: string): void {
    this.activeTime.set(time);
    afterNextRender(
      () => {
        this.host.nativeElement
          .querySelector(`#${this.optionId(time)}`)
          ?.scrollIntoView({ block: 'nearest' });
      },
      { injector: this.injector },
    );
  }

  /** Closes the list; the box keeps the chosen time and, unless it went elsewhere, the focus. */
  private close(returnFocus: boolean): void {
    this.open.set(false);
    this.text.set(this.value());
    this.touched.emit();
    if (returnFocus) {
      this.box()?.focus();
    }
  }

  private box(): HTMLInputElement | null {
    return this.host.nativeElement.querySelector<HTMLInputElement>(`#${this.inputId()}`);
  }

  private contains(target: EventTarget | null): boolean {
    return target instanceof Node && this.host.nativeElement.contains(target);
  }
}

/** `HH:MM` for a time typed as `9:30`, `09:30` or `0930`, or `null` when it is not one. */
export function parseTime(text: string): string | null {
  const match = /^(\d{1,2}):?(\d{2})$/.exec(text.trim());
  if (match === null) {
    return null;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  return hours < 24 && minutes < 60 ? clockTime(hours * 60 + minutes) : null;
}

/** The first time of the list at or after `time`, wrapping to 00:00 at the end of the day. */
function nearestListedTime(time: string): string {
  const [hours, minutes] = time.split(':').map(Number) as [number, number];
  const index = Math.ceil((hours * 60 + minutes) / STEP_MINUTES) % TIMES.length;
  return TIMES[index] ?? MIDNIGHT;
}

function minutesOfDay(date: Date): number {
  return date.getHours() * 60 + date.getMinutes();
}

function clockTime(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  return `${String(hours).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
}
