import {
  Component,
  computed,
  inject,
  input,
  linkedSignal,
  type OnInit,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { TenantContext } from '@core/tenant/tenant-context';
import { Button } from '@shared/ui/button';
import { DatePicker } from '@shared/ui/date-picker';
import { TextField } from '@shared/ui/text-field';
import { formatLocalDateTime, localTimeOf } from '@shared/utils/local-date-time';

import { problemMessageKey } from './problem-message';
import { SettingsNoAccess } from './settings-no-access';
import { SettingsTabs } from './settings-tabs';
import { SprintSettingsFacade } from '../application/sprint-settings.facade';
import { TeamShellFacade } from '../application/team-shell.facade';
import { keepMembers, moveDown, moveUp, toggleParticipant } from '../domain/daily-order';
import {
  areSprintFieldsValid,
  sprintFieldsProblems,
  type SprintFields,
} from '../domain/sprint-draft';

/** A turn of the daily as the order list shows it. */
interface Turn {
  readonly userId: string;
  readonly fullName: string;
  readonly position: number;
}

/**
 * Settings → Sprint: the period of the active sprint, the daily's time and who takes part in it,
 * in turn order. The form starts from what the API has (or empty, when the team has no active
 * sprint) and saving creates or edits the sprint. The daily's time is typed and shown in the
 * browser's time zone and saved with it (AD-31). The screen does not decide who may open it: it
 * shows "no access" when the API refuses the team, and translates the API's other refusals.
 */
@Component({
  selector: 'agl-team-sprint-settings-page',
  imports: [
    FormsModule,
    RouterLink,
    TranslocoDirective,
    Button,
    DatePicker,
    TextField,
    SettingsNoAccess,
    SettingsTabs,
  ],
  providers: [SprintSettingsFacade, TeamShellFacade],
  templateUrl: './team-sprint-settings-page.html',
})
export class TeamSprintSettingsPage implements OnInit {
  /** The :teamId of the route, bound by the router (withComponentInputBinding). */
  readonly teamId = input.required<string>();

  private readonly facade = inject(SprintSettingsFacade);
  private readonly shell = inject(TeamShellFacade);
  protected readonly tenant = inject(TenantContext);

  protected readonly sprint = this.facade.sprint;
  protected readonly members = this.facade.members;
  protected readonly ready = this.facade.ready;
  protected readonly loading = this.facade.loading;
  protected readonly saving = this.facade.saving;
  protected readonly browserTimeZone = this.facade.timeZone;
  /** The API refused the team to this user, when loading or saving: not an admin of it. */
  protected readonly forbidden = computed(
    () => this.facade.problem() === 'forbidden' || this.facade.saveProblem() === 'forbidden',
  );
  protected readonly problemMessage = computed(() =>
    this.forbidden() ? null : problemMessageKey(this.facade.problem()),
  );
  protected readonly saveMessage = computed(() => problemMessageKey(this.facade.saveProblem()));

  /**
   * The form as the saved sprint fills it (empty when the team has none): the starting point it
   * goes back to whenever the API answers another sprint, and what "changed" is measured from.
   */
  private readonly saved = computed<SprintFields>(() => {
    const sprint = this.sprint();
    return {
      startDate: sprint?.startDate ?? '',
      endDate: sprint?.endDate ?? '',
      // The time the person will see the daily at: the next one, or the anchor once none is left.
      dailyTime:
        sprint === undefined || sprint === null
          ? ''
          : localTimeOf(sprint.nextDailyAt ?? sprint.dailyTime),
      // In turn order; someone who is no longer a member is left out.
      participants: keepMembers(
        sprint?.participants ?? [],
        (this.members() ?? []).map((member) => member.userId),
      ),
    };
  });
  protected readonly startDate = linkedSignal(() => this.saved().startDate);
  protected readonly endDate = linkedSignal(() => this.saved().endDate);
  protected readonly dailyTime = linkedSignal(() => this.saved().dailyTime);
  /** The participants in turn order. */
  protected readonly order = linkedSignal(() => this.saved().participants);

  /** Whether the person already changed each part or left it: errors wait until then. */
  protected readonly startTouched = signal(false);
  protected readonly endTouched = signal(false);
  protected readonly timeTouched = signal(false);
  protected readonly participantsTouched = signal(false);
  private readonly problems = computed(() =>
    sprintFieldsProblems({
      startDate: this.startDate(),
      endDate: this.endDate(),
      dailyTime: this.dailyTime(),
      participants: this.order(),
    }),
  );
  protected readonly canSave = computed(() => areSprintFieldsValid(this.problems()));
  /** Whether the form differs from the saved sprint, in anything that is saved with it. */
  protected readonly hasChanges = computed(() => {
    const saved = this.saved();
    return (
      this.startDate() !== saved.startDate ||
      this.endDate() !== saved.endDate ||
      this.dailyTime() !== saved.dailyTime ||
      !sameOrder(this.order(), saved.participants)
    );
  });
  /** Saving makes sense with something valid and new to save: no changes, nothing to send. */
  protected readonly canSubmit = computed(() => this.canSave() && this.hasChanges());
  protected readonly startProblem = computed(() =>
    this.startTouched() ? this.problems().startDate : null,
  );
  protected readonly endProblem = computed(() =>
    this.endTouched() ? this.problems().endDate : null,
  );
  protected readonly timeProblem = computed(() =>
    this.timeTouched() ? this.problems().dailyTime : null,
  );
  protected readonly participantsProblem = computed(() =>
    this.participantsTouched() ? this.problems().participants : null,
  );

  protected readonly turns = computed<readonly Turn[]>(() => {
    const names = new Map((this.members() ?? []).map((member) => [member.userId, member.fullName]));
    return this.order().map((userId, index) => ({
      userId,
      fullName: names.get(userId) ?? '',
      position: index + 1,
    }));
  });
  /** The last move, announced to screen readers: who now has which turn. */
  protected readonly lastMove = signal<Turn | null>(null);
  /** Whether the last save worked and nothing changed since. */
  protected readonly justSaved = signal(false);

  ngOnInit(): void {
    this.facade.follow(this.teamId);
    this.shell.follow(this.teamId);
  }

  protected isParticipant(userId: string): boolean {
    return this.order().includes(userId);
  }

  protected changeStartDate(value: string): void {
    this.startDate.set(value);
    this.startTouched.set(true);
    this.changed();
  }

  protected changeEndDate(value: string): void {
    this.endDate.set(value);
    this.endTouched.set(true);
    this.changed();
  }

  protected changeDailyTime(value: string): void {
    this.dailyTime.set(value);
    this.timeTouched.set(true);
    this.changed();
  }

  protected toggle(userId: string): void {
    this.order.update((order) => toggleParticipant(order, userId));
    this.participantsTouched.set(true);
    this.lastMove.set(null);
    this.changed();
  }

  protected moveUp(userId: string): void {
    this.move(moveUp(this.order(), userId), userId);
  }

  protected moveDown(userId: string): void {
    this.move(moveDown(this.order(), userId), userId);
  }

  /** An instant, in the browser's time zone and the active language. */
  protected formatInstant(instant: string, language: string): string {
    return formatLocalDateTime(instant, language);
  }

  protected async submit(): Promise<void> {
    if (!this.canSubmit() || this.saving()) {
      return;
    }
    const saved = await this.facade.save({
      startDate: this.startDate(),
      endDate: this.endDate(),
      dailyTime: this.dailyTime(),
      participants: this.order(),
    });
    this.justSaved.set(saved);
  }

  private move(order: readonly string[], userId: string): void {
    this.order.set(order);
    this.lastMove.set(this.turns().find((turn) => turn.userId === userId) ?? null);
    this.changed();
  }

  private changed(): void {
    this.justSaved.set(false);
  }
}

/** Whether two lists of participants hold the same people in the same turn order. */
function sameOrder(first: readonly string[], second: readonly string[]): boolean {
  return first.length === second.length && first.every((userId, index) => userId === second[index]);
}
