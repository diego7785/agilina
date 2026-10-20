import {
  Component,
  computed,
  ElementRef,
  inject,
  input,
  linkedSignal,
  model,
  output,
} from '@angular/core';

import { ComboBox, type ComboOption } from './combo-box';

type Period = 'AM' | 'PM';

/** The parts of a time as the person sees them; empty while not chosen. */
interface TimeParts {
  readonly hour: string;
  readonly minute: string;
  readonly period: string;
}

const HOURS: readonly ComboOption[] = [...Array(12).keys()].map((index) => twoDigits(index + 1));
const MINUTES: readonly ComboOption[] = [...Array(60).keys()].map((index) => twoDigits(index));
const EMPTY: TimeParts = { hour: '', minute: '', period: '' };

/**
 * A time of the day (`HH:MM`, 24 hours) chosen in three boxes, the hour (1 to 12), the minutes
 * (00 to 59) and a. m. or p. m.: each one is typed or picked from its list (`agl-combo-box`).
 * It holds a time only once the three are chosen, and all three start empty when `value` is, so
 * nothing looks chosen before the person chooses it. It replaces `<input type="time">`, which in
 * Safari has no picker and, empty, paints the current time as if it were chosen.
 *
 * ```html
 * <label for="daily-time">Hora</label>
 * <agl-time-picker inputId="daily-time" [(value)]="dailyTime" [hourLabel]="t('hour')"
 *   [minuteLabel]="t('minutes')" [periodLabel]="t('period')" [amLabel]="t('am')"
 *   [pmLabel]="t('pm')" />
 * ```
 *
 * The `<label for>` names the hour box; `touched` tells that the focus left the three.
 */
@Component({
  selector: 'agl-time-picker',
  imports: [ComboBox],
  templateUrl: './time-picker.html',
  host: {
    class: 'block',
    role: 'group',
    '[attr.data-value]': 'value()',
    '(focusout)': 'onFocusOut($event)',
  },
})
export class TimePicker {
  /** The id of the hour box, which the `<label for>` points at; the others add a suffix. */
  readonly inputId = input.required<string>();
  /** The chosen time, `HH:MM` in 24 hours, or empty until the three parts are chosen. */
  readonly value = model('');
  readonly hourLabel = input.required<string>();
  readonly minuteLabel = input.required<string>();
  readonly periodLabel = input.required<string>();
  readonly amLabel = input.required<string>();
  readonly pmLabel = input.required<string>();
  /** Whether the boxes show as invalid (`aria-invalid`). */
  readonly invalid = input(false);
  /** The ids of the elements that describe the boxes, such as their error message. */
  readonly describedBy = input<string>();
  /** The `data-testid` of the hour box; the others add `-minute` and `-period`. */
  readonly testId = input<string>();
  /** The focus left the three boxes. */
  readonly touched = output();

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly hours = HOURS;
  protected readonly minutes = MINUTES;
  protected readonly periods = computed<readonly ComboOption[]>(() => [
    { value: 'AM', label: this.amLabel() },
    { value: 'PM', label: this.pmLabel() },
  ]);
  protected readonly parseHour = (text: string): string | null => numberIn(text, 1, 12);
  protected readonly parseMinute = (text: string): string | null => numberIn(text, 0, 59);
  protected readonly parsePeriod = parsePeriod;

  /**
   * What each box holds: what the person chose so far while it still makes `value` (so clearing
   * the hour keeps the minutes), or the parts of a `value` that came from outside.
   */
  protected readonly parts = linkedSignal<string, TimeParts>({
    source: this.value,
    computation: (value, previous) =>
      previous !== undefined && timeOf(previous.value) === value ? previous.value : partsOf(value),
  });

  protected suffixed(id: string | undefined, suffix: string): string | undefined {
    return id === undefined ? undefined : `${id}-${suffix}`;
  }

  protected choose(part: keyof TimeParts, chosen: string): void {
    const parts = { ...this.parts(), [part]: chosen };
    this.parts.set(parts);
    this.value.set(timeOf(parts));
  }

  protected onFocusOut(event: FocusEvent): void {
    const next = event.relatedTarget;
    if (!(next instanceof Node && this.host.nativeElement.contains(next))) {
      this.touched.emit();
    }
  }
}

/** `HH:MM` in 24 hours once the three parts are chosen, or empty. */
function timeOf({ hour, minute, period }: TimeParts): string {
  if (hour === '' || minute === '' || period === '') {
    return '';
  }
  const hours = (Number(hour) % 12) + (period === 'PM' ? 12 : 0);
  return `${String(hours).padStart(2, '0')}:${minute}`;
}

function partsOf(value: string): TimeParts {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (match === null) {
    return EMPTY;
  }
  const hours = Number(match[1]);
  const period: Period = hours < 12 ? 'AM' : 'PM';
  return {
    hour: twoDigits(hours % 12 === 0 ? 12 : hours % 12).value,
    minute: match[2] ?? '',
    period,
  };
}

/** The two-digit value of a whole number between `min` and `max` typed in `text`, or `null`. */
function numberIn(text: string, min: number, max: number): string | null {
  const trimmed = text.trim();
  if (!/^\d{1,2}$/.test(trimmed)) {
    return null;
  }
  const number = Number(trimmed);
  return number >= min && number <= max ? twoDigits(number).value : null;
}

/** AM or PM for what starts with an a or a p (`a. m.`, `AM`, `p`), or `null`. */
function parsePeriod(text: string): Period | null {
  const letter = text.trim().toLowerCase().charAt(0);
  if (letter === 'a') {
    return 'AM';
  }
  return letter === 'p' ? 'PM' : null;
}

function twoDigits(number: number): ComboOption {
  const text = String(number).padStart(2, '0');
  return { value: text, label: text };
}
