import { TestBed } from '@angular/core/testing';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { NEVER, of, Subject, throwError, type Observable } from 'rxjs';

import { Notifier } from '@core/notifications/notifier';
import { ShellContext } from '@core/shell/shell-context';
import { BROWSER_TIME_ZONE } from '@core/time/browser-time-zone';
import { provideTestI18n } from '@testing/i18n';
import { aTeam } from '@testing/team';
import { provideTestTenant } from '@testing/tenant';

import { TeamSprintSettingsPage } from './team-sprint-settings-page';
import { SprintsPort } from '../application/sprints.port';
import { TeamsPort } from '../application/teams.port';
import { UsersPort } from '../application/users.port';
import { type ActiveSprint } from '../domain/active-sprint';
import { MemberFailure } from '../domain/member-failure';
import { type SprintDraft } from '../domain/sprint-draft';
import { SprintFailure } from '../domain/sprint-failure';
import { type Team } from '../domain/team';
import { type MyMembership, type TeamMember, type TeamMembers } from '../domain/team-member';

function member(userId: string, fullName: string): TeamMember {
  return {
    userId,
    fullName,
    email: `${userId}@example.com`,
    role: 'member',
    label: 'member',
    joinedAt: new Date('2026-10-08T15:04:05Z'),
    roleChangeBlockedBy: null,
    removalBlockedBy: null,
  };
}

const ANA = member('ana', 'Ana Gil');
const BRUNO = member('bruno', 'Bruno Díaz');
const CARLA = member('carla', 'Carla Ruiz');

/*
 * The instants are built from wall-clock times in the zone of whoever runs the tests, so the
 * time the page shows is the same on any machine: the page always works in the browser's zone.
 */
const SPRINT: ActiveSprint = {
  id: 'sprint-1',
  number: 12,
  startDate: '2026-10-05',
  endDate: '2026-10-16',
  dailyTime: new Date(2026, 9, 5, 9, 0).toISOString(),
  timeZone: 'America/Bogota',
  nextDailyAt: new Date(2026, 9, 8, 9, 0).toISOString(),
  participants: ['bruno', 'ana'],
  day: { number: 3, total: 12, phase: 'in_progress' },
};

/**
 * Sprints port double: active() answers what `current` holds (nothing yet for the team 'slow');
 * start() and reconfigure() wait until the test answers them.
 */
class FakeSprintsPort extends SprintsPort {
  current: ActiveSprint | null | SprintFailure = SPRINT;
  readonly read: string[] = [];
  readonly started: SprintDraft[] = [];
  readonly reconfigured: SprintDraft[] = [];
  private pending = new Subject<ActiveSprint>();

  active(teamId: string): Observable<ActiveSprint | null> {
    this.read.push(teamId);
    if (teamId === 'slow') {
      return NEVER;
    }
    const current = this.current;
    return current instanceof SprintFailure ? throwError(() => current) : of(current);
  }

  start(teamId: string, draft: SprintDraft): Observable<ActiveSprint> {
    this.started.push(draft);
    return this.command();
  }

  reconfigure(teamId: string, draft: SprintDraft): Observable<ActiveSprint> {
    this.reconfigured.push(draft);
    return this.command();
  }

  /** The API saves the sprint and answers it. */
  accept(sprint: ActiveSprint): void {
    this.pending.next(sprint);
    this.pending.complete();
  }

  /** The API refuses the save. */
  refuse(failure: Error): void {
    this.pending.error(failure);
  }

  private command(): Observable<ActiveSprint> {
    this.pending = new Subject<ActiveSprint>();
    return this.pending;
  }
}

/** Members port double: list() answers `answer`; the sprint screen uses nothing else. */
class FakeUsersPort extends UsersPort {
  answer: TeamMembers | MemberFailure = { roles: [], members: [ANA, BRUNO, CARLA] };

  list(): Observable<TeamMembers> {
    const answer = this.answer;
    return answer instanceof MemberFailure ? throwError(() => answer) : of(answer);
  }

  get(): Observable<never> {
    return NEVER;
  }

  me(): Observable<MyMembership> {
    return of({
      userId: 'ana',
      fullName: 'Ana Gil',
      email: 'ana@example.com',
      role: 'admin',
      label: 'scrum_master',
      joinedAt: new Date('2026-10-08T15:04:05Z'),
    });
  }

  invite(): Observable<never> {
    return NEVER;
  }

  changeRole(): Observable<never> {
    return NEVER;
  }

  remove(): Observable<never> {
    return NEVER;
  }
}

/** The team of the screen, read for the top bar. */
class FakeTeamsPort extends TeamsPort {
  dashboard(): Observable<never> {
    return NEVER;
  }

  listMine(): Observable<never> {
    return NEVER;
  }

  create(): Observable<never> {
    return NEVER;
  }

  get(teamId: string): Observable<Team> {
    return of(aTeam(teamId, 'Atlas'));
  }
}

describe('TeamSprintSettingsPage', () => {
  let sprints: FakeSprintsPort;
  let members: FakeUsersPort;
  let harness: RouterTestingHarness;
  let page: HTMLElement;

  beforeEach(async () => {
    sprints = new FakeSprintsPort();
    members = new FakeUsersPort();
    TestBed.configureTestingModule({
      providers: [
        provideTestI18n(),
        provideTestTenant(),
        provideRouter(
          [{ path: ':tenant/teams/:teamId/settings/sprint', component: TeamSprintSettingsPage }],
          withComponentInputBinding(),
        ),
        { provide: SprintsPort, useValue: sprints },
        { provide: UsersPort, useValue: members },
        { provide: TeamsPort, useClass: FakeTeamsPort },
        // The browser of whoever opens the screen, fixed: not the zone of the machine.
        { provide: BROWSER_TIME_ZONE, useValue: 'America/Bogota' },
      ],
    });
    harness = await RouterTestingHarness.create();
  });

  async function open(url = '/acme/teams/atlas/settings/sprint'): Promise<void> {
    await harness.navigateByUrl(url);
    await harness.fixture.whenStable();
    page = harness.routeNativeElement!;
  }

  /** Lets the page react to an answer the facade awaited (see CreateTeamPage's spec). */
  async function settled(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await harness.fixture.whenStable();
  }

  function text(element: Element | null | undefined): string {
    return element?.textContent.replace(/\s+/g, ' ').trim() ?? '';
  }

  /** The control a `<label for>` with this text names. */
  function field(label: string): HTMLInputElement {
    const found = Array.from(page.querySelectorAll('label[for]')).find(
      (candidate) => text(candidate) === label,
    );
    expect(found).withContext(`a label "${label}"`).toBeDefined();
    return page.querySelector<HTMLInputElement>(`#${found!.getAttribute('for')!}`)!;
  }

  /** The calendar date a date box holds (`YYYY-MM-DD`), or empty. */
  function dateIn(label: string): string {
    return field(label).getAttribute('data-value') ?? '';
  }

  /** The day of the open calendar for a calendar date, if the month it shows has it. */
  function calendarDay(date: string): HTMLButtonElement | null {
    return page.querySelector<HTMLButtonElement>(`[role="dialog"] button[data-date="${date}"]`);
  }

  /** Opens the calendar of a date box, goes to the month of `date` and picks that day. */
  async function pickDate(label: string, date: string): Promise<void> {
    field(label).click();
    await harness.fixture.whenStable();
    for (let step = 0; step < 36 && calendarDay(date) === null; step++) {
      const shown = page
        .querySelector('[role="dialog"] button[data-date]')!
        .getAttribute('data-date')!
        .slice(0, 7);
      const towards = date.slice(0, 7) > shown ? 'Mes siguiente' : 'Mes anterior';
      page
        .querySelector<HTMLButtonElement>(`[role="dialog"] button[aria-label="${towards}"]`)!
        .click();
      await harness.fixture.whenStable();
    }
    calendarDay(date)!.click();
    await harness.fixture.whenStable();
  }

  async function type(control: HTMLInputElement, value: string): Promise<void> {
    control.value = value;
    control.dispatchEvent(new Event('input'));
    await harness.fixture.whenStable();
  }

  /** The three boxes of the daily's time: hour, minutes and a. m. or p. m. */
  function timeBoxes(): [HTMLInputElement, HTMLInputElement, HTMLInputElement] {
    return [
      field('Hora de la reunión diaria'),
      page.querySelector<HTMLInputElement>('#sprint-daily-time-minute')!,
      page.querySelector<HTMLInputElement>('#sprint-daily-time-period')!,
    ];
  }

  /** The daily's time the form holds (`HH:MM`), or empty while a part is missing. */
  function timeIn(): string {
    return page.querySelector('agl-time-picker')!.getAttribute('data-value') ?? '';
  }

  /** Types a time (`HH:MM`, 24 hours) in the three boxes; an empty one clears the hour. */
  async function setTime(time: string): Promise<void> {
    const [hour, minute, period] = timeBoxes();
    if (time === '') {
      await type(hour, '');
      return;
    }
    const [hours, minutes] = time.split(':').map(Number) as [number, number];
    await type(hour, String(hours % 12 === 0 ? 12 : hours % 12));
    await type(minute, String(minutes).padStart(2, '0'));
    await type(period, hours < 12 ? 'a. m.' : 'p. m.');
  }

  /** The checkbox of a member among the daily's participants. */
  function checkbox(name: string): HTMLInputElement {
    const found = Array.from(page.querySelectorAll('fieldset label')).find(
      (candidate) => text(candidate) === name,
    );
    expect(found).withContext(`a participant "${name}"`).toBeDefined();
    return found!.querySelector('input[type="checkbox"]')!;
  }

  async function toggle(name: string): Promise<void> {
    checkbox(name).click();
    await harness.fixture.whenStable();
  }

  /** The names in the turn order, first speaker first, with their position. */
  function turns(): string[] {
    return Array.from(page.querySelectorAll('ol li')).map((row) => text(row));
  }

  function moveButton(direction: 'Subir' | 'Bajar', name: string): HTMLButtonElement {
    return page.querySelector<HTMLButtonElement>(`button[aria-label="${direction} a ${name}"]`)!;
  }

  /** What the live regions announce to a screen reader. */
  function announcements(): string[] {
    return Array.from(page.querySelectorAll('[aria-live="polite"]')).map((region) => text(region));
  }

  /** What the page asked the notifier to show: the toasts, which the page does not draw. */
  function notices(): { kind: string; message: string }[] {
    return TestBed.inject(Notifier)
      .notifications()
      .map(({ kind, message }) => ({ kind, message }));
  }

  function submitButton(): HTMLButtonElement {
    return page.querySelector<HTMLButtonElement>('button[type="submit"]')!;
  }

  async function submit(): Promise<void> {
    submitButton().click();
    await harness.fixture.whenStable();
  }

  /** The time of the daily the form starts with: 09:00. A different one is something to save. */

  async function makeChange(time = '10:30'): Promise<void> {
    await setTime(time);
  }

  /** The sprint the API answers once the daily moved to 10:30. */
  const savedAtTenThirty: ActiveSprint = {
    ...SPRINT,
    nextDailyAt: new Date(2026, 9, 8, 10, 30).toISOString(),
  };

  // --------------------------------------------------------------- the screen --
  it('is the Sprint tab of the settings, with the active sprint marked and numbered', async () => {
    await open();

    expect(sprints.read).toEqual(['atlas']);
    expect(text(page.querySelector('h1'))).toBe('Configuración');
    expect(text(page.querySelector('nav a[aria-current="page"]'))).toBe('Sprint');
    expect(text(page.querySelector('h2'))).toBe('Sprint 12');
    expect(text(page)).toContain('Sprint activo');
    expect(page.querySelector('a[href="/acme/teams/atlas"]')).not.toBeNull();
  });

  it('titles the card with the number of the sprint, and plain "Sprint" while there is none', async () => {
    await open();
    expect(text(page.querySelector('[data-testid="sprint-title"]'))).toBe('Sprint 12');
  });

  it('has no number to show while the team has no sprint: the API gives it on saving', async () => {
    sprints.current = null;

    await open();

    expect(text(page.querySelector('[data-testid="sprint-title"]'))).toBe('Sprint');
    expect(text(page)).not.toMatch(/Sprint \d/);
  });

  it('shows the number of the sprint the API answers after saving it', async () => {
    sprints.current = null;
    await open();
    await pickDate('Inicio', '2026-10-19');
    await pickDate('Fin', '2026-10-30');
    await setTime('09:30');
    await toggle('Ana Gil');
    await submit();

    sprints.accept({ ...SPRINT, id: 'sprint-2', number: 13 });
    await settled();

    expect(text(page.querySelector('[data-testid="sprint-title"]'))).toBe('Sprint 13');
  });

  it('configures only the daily: no retro and no review', async () => {
    await open();

    expect(text(page)).not.toMatch(/retro|review/i);
  });

  it('does not mark the sprint as active while the team has none, and starts empty', async () => {
    sprints.current = null;
    await open();

    expect(text(page)).not.toContain('Sprint activo');
    expect(dateIn('Inicio')).toBe('');
    expect(dateIn('Fin')).toBe('');
    expect(text(field('Inicio'))).toBe('Elige una fecha');
    expect(timeBoxes().map((box) => box.value)).toEqual(['', '', '']);
    expect(checkbox('Ana Gil').checked).toBeFalse();
    expect(turns()).toEqual([]);
    expect(text(page)).toContain(
      'Marca a los participantes de la reunión diaria para ordenar sus turnos.',
    );
    expect(submitButton().disabled).toBeTrue();
  });

  it('says it is loading while the API has not answered', async () => {
    await harness.navigateByUrl('/acme/teams/slow/settings/sprint');
    TestBed.tick();
    page = harness.routeNativeElement!;

    expect(text(page.querySelector('[role="status"]'))).toBe('Cargando el sprint…');
    expect(page.querySelector('form')).toBeNull();
  });

  // ------------------------------------------------- criteria 1, 2 and 3b ------
  it('fills the form with the saved dates and the daily time in the browser zone', async () => {
    await open();

    expect(field('Inicio').getAttribute('aria-haspopup')).toBe('dialog');
    expect(dateIn('Inicio')).toBe('2026-10-05');
    expect(text(field('Inicio'))).toBe('5 de octubre de 2026');
    expect(dateIn('Fin')).toBe('2026-10-16');
    expect(field('Hora de la reunión diaria').getAttribute('role')).toBe('combobox');
    expect(timeBoxes().map((box) => box.value)).toEqual(['09', '00', 'a. m.']);
    expect(timeIn()).toBe('09:00');
  });

  it('shows the time of the anchor when no daily is left in the sprint', async () => {
    sprints.current = {
      ...SPRINT,
      dailyTime: new Date(2026, 9, 5, 8, 15).toISOString(),
      nextDailyAt: null,
      day: { number: 12, total: 12, phase: 'finished' },
    };
    await open();

    expect(timeIn()).toBe('08:15');
  });

  it('says the times are in the browser zone and the zone the daily was saved in', async () => {
    await open();

    expect(text(page)).toContain(
      'Las horas se muestran en la zona horaria de tu navegador (America/Bogota).',
    );
    expect(text(page)).toContain(
      'La hora de la reunión diaria está guardada en la zona America/Bogota.',
    );
    expect(text(page)).not.toContain('Próxima daily');
    expect(text(page)).not.toContain('Ya no quedan dailies');
    expect(text(page)).not.toContain('pasará a la zona de tu navegador');
  });

  it('warns that saving moves the daily to the browser zone when it was saved in another', async () => {
    sprints.current = { ...SPRINT, timeZone: 'Europe/Madrid' };
    await open();

    expect(text(page)).toContain(
      'La hora de la reunión diaria está guardada en la zona Europe/Madrid.',
    );
    expect(text(page)).toContain(
      'Al guardar, la hora de la reunión diaria pasará a la zona de tu navegador.',
    );
  });

  it('ties the zone of the browser to the time control', async () => {
    await open();

    const described = field('Hora de la reunión diaria')
      .getAttribute('aria-describedby')!
      .split(' ')
      .map((id) => text(page.querySelector(`#${id}`)));
    expect(described).toContain(
      'Las horas se muestran en la zona horaria de tu navegador (America/Bogota).',
    );
  });

  it('does not accept an end before the start, and says why', async () => {
    await open();

    await pickDate('Inicio', '2026-10-20');
    field('Fin').dispatchEvent(new Event('blur'));
    await harness.fixture.whenStable();

    expect(field('Fin').getAttribute('aria-invalid')).toBe('true');
    expect(text(page)).toContain('La fecha de fin no puede ser anterior a la de inicio.');
    expect(submitButton().disabled).toBeTrue();
  });

  it('accepts an end on the same day as the start', async () => {
    await open();

    await pickDate('Fin', '2026-10-05');

    expect(field('Fin').getAttribute('aria-invalid')).toBe('false');
    expect(submitButton().disabled).toBeFalse();
  });

  it('asks for a date and the time once the person leaves them empty', async () => {
    sprints.current = null;
    await open();

    field('Inicio').click();
    await harness.fixture.whenStable();
    page
      .querySelector('[role="dialog"]')!
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await harness.fixture.whenStable();
    field('Hora de la reunión diaria').dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
    await harness.fixture.whenStable();

    expect(text(page)).toContain('Elige la fecha de inicio.');
    expect(text(page)).toContain('Elige la hora de la reunión diaria.');
    expect(submitButton().disabled).toBeTrue();
  });

  it('asks for the end date once the person leaves it, not before', async () => {
    sprints.current = null;
    await open();
    expect(text(page)).not.toContain('Elige la fecha de fin.');

    field('Fin').dispatchEvent(new Event('blur'));
    await harness.fixture.whenStable();

    expect(text(page)).toContain('Elige la fecha de fin.');
  });

  // ----------------------------------------------------------- criterion 3 --
  it('offers every member of the team as a participant and checks the saved ones', async () => {
    await open();

    expect(text(page.querySelector('#sprint-participants-title'))).toBe(
      'Participantes por ceremonia',
    );
    expect(text(page.querySelector('legend'))).toBe('Reunión diaria');
    expect(checkbox('Ana Gil').checked).toBeTrue();
    expect(checkbox('Bruno Díaz').checked).toBeTrue();
    expect(checkbox('Carla Ruiz').checked).toBeFalse();
  });

  it('groups the participants by ceremony and the daily is the only one', async () => {
    await open();

    const card = page.querySelector('[data-testid="sprint-participants-card"]')!;
    expect(card.querySelectorAll('fieldset').length).toBe(1);
    expect(card.querySelectorAll('legend').length).toBe(1);
    expect(text(card)).not.toMatch(/retro|review/i);
    expect(card.querySelectorAll('input[type="checkbox"]').length).toBe(3);
  });

  it('draws the participants checkboxes round', async () => {
    await open();

    const boxes = Array.from(
      page.querySelectorAll<HTMLInputElement>('[data-testid="sprint-participants-card"] input'),
    );
    expect(boxes.length).toBe(3);
    for (const box of boxes) {
      // A circle: the corners round off at least half the side.
      expect(box.offsetWidth).toBeGreaterThan(0);
      expect(parseFloat(getComputedStyle(box).borderTopLeftRadius)).toBeGreaterThanOrEqual(
        box.offsetWidth / 2,
      );
    }
  });

  it('adds a checked member at the end of the turns and takes an unchecked one out', async () => {
    await open();

    await toggle('Carla Ruiz');
    expect(turns()).toEqual(['1 Bruno Díaz', '2 Ana Gil', '3 Carla Ruiz']);

    await toggle('Bruno Díaz');
    expect(checkbox('Bruno Díaz').checked).toBeFalse();
    expect(turns()).toEqual(['1 Ana Gil', '2 Carla Ruiz']);
  });

  it('asks for at least one participant once the last one is unchecked', async () => {
    await open();

    await toggle('Ana Gil');
    await toggle('Bruno Díaz');

    expect(turns()).toEqual([]);
    expect(text(page)).toContain('Elige al menos un participante para la reunión diaria.');
    expect(submitButton().disabled).toBeTrue();
  });

  it('leaves out of the turns a saved participant who is no longer a member', async () => {
    sprints.current = { ...SPRINT, participants: ['bruno', 'gone', 'ana'] };
    await open();

    expect(turns()).toEqual(['1 Bruno Díaz', '2 Ana Gil']);
  });

  // ----------------------------------------------------------- criterion 4 --
  it('shows the saved participants in their turn order, numbered', async () => {
    await open();

    expect(text(page)).toContain('Orden de turnos de la reunión diaria');
    expect(turns()).toEqual(['1 Bruno Díaz', '2 Ana Gil']);
  });

  it('moves a participant up and down, and announces the new turn', async () => {
    await open();
    await toggle('Carla Ruiz');

    moveButton('Subir', 'Carla Ruiz').click();
    await harness.fixture.whenStable();
    expect(turns()).toEqual(['1 Bruno Díaz', '2 Carla Ruiz', '3 Ana Gil']);
    expect(announcements()).toContain('Carla Ruiz ahora tiene el turno 2.');

    moveButton('Bajar', 'Bruno Díaz').click();
    await harness.fixture.whenStable();
    expect(turns()).toEqual(['1 Carla Ruiz', '2 Bruno Díaz', '3 Ana Gil']);
    expect(announcements()).toContain('Bruno Díaz ahora tiene el turno 2.');
  });

  it('cannot move the first one up nor the last one down', async () => {
    await open();
    await toggle('Carla Ruiz');

    expect(moveButton('Subir', 'Bruno Díaz').disabled).toBeTrue();
    expect(moveButton('Bajar', 'Bruno Díaz').disabled).toBeFalse();
    expect(moveButton('Subir', 'Ana Gil').disabled).toBeFalse();
    expect(moveButton('Bajar', 'Ana Gil').disabled).toBeFalse();
    expect(moveButton('Subir', 'Carla Ruiz').disabled).toBeFalse();
    expect(moveButton('Bajar', 'Carla Ruiz').disabled).toBeTrue();
  });

  // ------------------------------------------------------- saving (CA1–CA5) --
  it('starts the hour, the minutes and a. m. or p. m. empty when the team has no sprint', async () => {
    sprints.current = null;
    await open();

    expect(timeBoxes().map((box) => box.value)).toEqual(['', '', '']);
    expect(timeBoxes().map((box) => box.getAttribute('aria-label'))).toEqual([
      'Hora',
      'Minutos',
      'a. m. o p. m.',
    ]);
    expect(timeIn()).toBe('');
  });

  it('keeps no time until the hour, the minutes and a. m. or p. m. are all chosen', async () => {
    sprints.current = null;
    await open();
    const [hour, minute, period] = timeBoxes();

    await type(hour, '2');
    await type(minute, '45');
    expect(timeIn()).toBe('');

    await type(period, 'p');
    expect(timeIn()).toBe('14:45');
  });

  it('creates the sprint when the team has none, with the daily in UTC and the browser zone', async () => {
    sprints.current = null;
    await open();

    await pickDate('Inicio', '2026-10-19');
    await pickDate('Fin', '2026-10-30');
    await setTime('09:30');
    await toggle('Carla Ruiz');
    await toggle('Ana Gil');
    await submit();

    expect(sprints.reconfigured).toEqual([]);
    expect(sprints.started).toEqual([
      {
        startDate: '2026-10-19',
        endDate: '2026-10-30',
        dailyTime: new Date(2026, 9, 19, 9, 30).toISOString(),
        timeZone: 'America/Bogota',
        participants: ['carla', 'ana'],
      },
    ]);
    expect(sprints.started[0]?.dailyTime).toMatch(/Z$/);

    sprints.accept({
      ...SPRINT,
      id: 'sprint-2',
      startDate: '2026-10-19',
      endDate: '2026-10-30',
      participants: ['carla', 'ana'],
    });
    await settled();

    expect(notices()).toEqual([{ kind: 'success', message: 'Sprint guardado.' }]);
    expect(text(page)).not.toContain('Sprint guardado.');
    expect(text(page)).toContain('Sprint activo');
    expect(turns()).toEqual(['1 Carla Ruiz', '2 Ana Gil']);
    expect(page.querySelector('[role="alert"]')).toBeNull();
  });

  it('edits the active sprint with the new order of the turns', async () => {
    await open();

    moveButton('Subir', 'Ana Gil').click();
    await harness.fixture.whenStable();
    await submit();

    expect(sprints.started).toEqual([]);
    expect(sprints.reconfigured).toEqual([
      {
        startDate: '2026-10-05',
        endDate: '2026-10-16',
        dailyTime: new Date(2026, 9, 5, 9, 0).toISOString(),
        timeZone: 'America/Bogota',
        participants: ['ana', 'bruno'],
      },
    ]);
  });

  it('is saving meanwhile: it cannot be sent again nor the turns moved', async () => {
    await open();
    await makeChange();

    await submit();

    expect(text(submitButton())).toBe('Guardando…');
    expect(submitButton().disabled).toBeTrue();
    expect(moveButton('Bajar', 'Bruno Díaz').disabled).toBeTrue();
    await submit();
    expect(sprints.reconfigured.length).toBe(1);

    sprints.accept(savedAtTenThirty);
    await settled();
    expect(text(submitButton())).toBe('Guardar');
    // What was in the form is now the saved sprint: nothing is left to save.
    expect(submitButton().disabled).toBeTrue();
  });

  it('confirms the save with a toast and writes nothing in the page, whatever changes after', async () => {
    await open();
    await makeChange();
    await submit();
    sprints.accept(savedAtTenThirty);
    await settled();
    expect(notices()).toEqual([{ kind: 'success', message: 'Sprint guardado.' }]);

    await toggle('Carla Ruiz');

    expect(text(page)).not.toContain('Sprint guardado.');
    expect(page.querySelector('[role="status"]')).toBeNull();
    expect(notices().length).toBe(1);
  });

  it('does not confirm anything before the API answers', async () => {
    await open();
    await makeChange();

    await submit();

    expect(notices()).toEqual([]);
  });

  const refusals: [string, string][] = [
    ['ends_before_start', 'La fecha de fin no puede ser anterior a la de inicio.'],
    [
      'invalid_time_zone',
      'La zona horaria de tu navegador no es una zona válida. Revisa la configuración de tu dispositivo.',
    ],
    ['no_participants', 'Elige al menos un participante para la reunión diaria.'],
    ['duplicate_participant', 'Un participante aparece más de una vez.'],
    [
      'participant_not_a_member',
      'Uno de los participantes ya no es integrante del equipo. Recarga la página y vuelve a elegirlos.',
    ],
    [
      'active_sprint_exists',
      'Alguien más configuró el sprint del equipo mientras tanto. Revisa los datos y guarda de nuevo.',
    ],
    [
      'no_active_sprint',
      'El equipo ya no tiene un sprint activo. Revisa los datos y guarda de nuevo.',
    ],
    ['not_authenticated', 'Tu sesión no es válida o expiró. Inicia sesión de nuevo.'],
    ['unavailable', 'No se pudo guardar el sprint. Inténtalo de nuevo.'],
  ];

  refusals.forEach(([kind, message]) => {
    it(`says why the API refused the sprint (${kind}), as an error toast`, async () => {
      await open();
      await makeChange();

      await submit();
      sprints.refuse(new SprintFailure(kind as SprintFailure['kind']));
      await settled();

      expect(notices()).toEqual([{ kind: 'error', message }]);
      expect(page.querySelector('[role="alert"]')).toBeNull();
      expect(text(page)).not.toContain(message);
      expect(page.querySelector('form')).not.toBeNull();
    });
  });

  // ------------------------------------------------------------- no access --
  it('shows "no access" when the API refuses the screen to this user', async () => {
    members.answer = new MemberFailure('forbidden');
    await open();

    expect(text(page.querySelector('[data-testid="settings-forbidden-title"]'))).toBe(
      'No tienes acceso a esta pantalla',
    );
    expect(text(page)).toContain(
      'Solo los Administradores del equipo pueden configurar el sprint.',
    );
    expect(page.querySelector('form')).toBeNull();
    expect(page.querySelector('nav')).toBeNull();
    expect(page.querySelector('a[href="/acme/teams/atlas"]')).not.toBeNull();
  });

  it('shows "no access" when the API refuses the sprint itself', async () => {
    sprints.current = new SprintFailure('forbidden');
    await open();

    expect(page.querySelector('[data-testid="settings-forbidden-title"]')).not.toBeNull();
    expect(page.querySelector('form')).toBeNull();
  });

  it('shows "no access" when the API refuses the save: the admin lost the role meanwhile', async () => {
    await open();
    await makeChange();

    await submit();
    sprints.refuse(new SprintFailure('forbidden'));
    await settled();

    expect(page.querySelector('[data-testid="settings-forbidden-title"]')).not.toBeNull();
    expect(page.querySelector('form')).toBeNull();
  });

  it('asks to sign in again when the API does not recognise the session', async () => {
    sprints.current = new SprintFailure('not_authenticated');
    await open();

    expect(text(page.querySelector('[role="alert"]'))).toBe(
      'Tu sesión no es válida o expiró. Inicia sesión de nuevo.',
    );
    expect(page.querySelector('form')).toBeNull();
  });

  it('shows a generic message when the screen cannot be loaded for another reason', async () => {
    members.answer = new MemberFailure('unavailable');
    await open();

    expect(text(page.querySelector('[role="alert"]'))).toBe(
      'No se pudo cargar el sprint. Inténtalo de nuevo más tarde.',
    );
    expect(page.querySelector('form')).toBeNull();
  });

  it('puts the team and how the user is called in it in the top bar, like the other team screens', async () => {
    await open();

    expect(TestBed.inject(ShellContext).team()).toEqual({
      id: 'atlas',
      name: 'Atlas',
      roleLabel: 'scrum_master',
      userName: 'Ana Gil',
      canConfigure: true,
    });
  });
  describe('the close sprint button', () => {
    it('is offered, as a card of its own, when the team has an active sprint', async () => {
      await open();

      expect(text(page.querySelector('[data-testid="sprint-close-title"]'))).toBe(
        'Cerrar sprint activo',
      );
      expect(text(page.querySelector('[data-testid="sprint-close-card"] p'))).toBe(
        'Se cerrarán las ceremonias pendientes y podrás editar roles y modo.',
      );
      const button = page.querySelector<HTMLButtonElement>('[data-testid="sprint-close-open"]');
      expect(text(button)).toBe('Cerrar sprint activo');
      expect(button?.type).toBe('button');
      expect(page.querySelector('form [data-testid="sprint-close-open"]')).toBeNull();
    });

    it('is not offered when the team has no active sprint: there is nothing to close', async () => {
      sprints.current = null;

      await open();

      expect(page.querySelector('form')).not.toBeNull();
      expect(page.querySelector('[data-testid="sprint-close-card"]')).toBeNull();
      expect(page.querySelector('[data-testid="sprint-close-open"]')).toBeNull();
    });

    it('does nothing yet when pressed: closing arrives with its own story', async () => {
      await open();
      const reads = sprints.read.length;

      page.querySelector<HTMLButtonElement>('[data-testid="sprint-close-open"]')!.click();
      await settled();

      expect(sprints.started).toEqual([]);
      expect(sprints.reconfigured).toEqual([]);
      expect(sprints.read.length).toBe(reads);
      expect(page.querySelector('[role="dialog"], dialog[open]')).toBeNull();
      expect(page.querySelector('[data-testid="sprint-active-badge"]')).not.toBeNull();
    });

    it('does not appear while the sprint is still loading', async () => {
      await harness.navigateByUrl('/acme/teams/slow/settings/sprint');
      TestBed.tick();
      page = harness.routeNativeElement!;

      expect(page.querySelector('[data-testid="sprint-close-card"]')).toBeNull();
    });
  });
  describe('the save button', () => {
    it('is off while nothing differs from the saved sprint', async () => {
      await open();

      expect(text(submitButton())).toBe('Guardar');
      expect(submitButton().disabled).toBeTrue();
    });

    it('turns on when the daily time changes, and off again when it goes back', async () => {
      await open();

      await makeChange('10:30');
      expect(submitButton().disabled).toBeFalse();

      await makeChange('09:00');
      expect(submitButton().disabled).toBeTrue();
    });

    it('turns on when a date changes', async () => {
      await open();

      await pickDate('Fin', '2026-10-20');

      expect(dateIn('Fin')).toBe('2026-10-20');
      expect(submitButton().disabled).toBeFalse();
    });

    it('turns on when a participant is added, and off again when they are taken out', async () => {
      await open();

      await toggle('Carla Ruiz');
      expect(submitButton().disabled).toBeFalse();

      await toggle('Carla Ruiz');
      expect(submitButton().disabled).toBeTrue();
    });

    it('turns on when the turns change places, and off again when they go back', async () => {
      await open();

      moveButton('Subir', 'Ana Gil').click();
      await harness.fixture.whenStable();
      expect(submitButton().disabled).toBeFalse();

      moveButton('Bajar', 'Ana Gil').click();
      await harness.fixture.whenStable();
      expect(submitButton().disabled).toBeTrue();
    });

    it('stays off when the change is not valid', async () => {
      await open();

      await makeChange('');

      expect(submitButton().disabled).toBeTrue();
    });

    it('does not send anything when pressed without changes', async () => {
      await open();

      await submit();

      expect(sprints.started).toEqual([]);
      expect(sprints.reconfigured).toEqual([]);
    });

    it('is off again once the change is saved, with the confirmation as a toast', async () => {
      await open();
      await makeChange();
      await submit();
      sprints.accept(savedAtTenThirty);
      await settled();

      expect(notices()).toEqual([{ kind: 'success', message: 'Sprint guardado.' }]);
      expect(submitButton().disabled).toBeTrue();
    });

    it('is off for a team with no sprint until the form is complete', async () => {
      sprints.current = null;
      await open();
      expect(submitButton().disabled).toBeTrue();

      await pickDate('Inicio', '2026-10-19');
      await pickDate('Fin', '2026-10-30');
      await makeChange('09:30');
      expect(submitButton().disabled).toBeTrue();

      await toggle('Ana Gil');
      expect(submitButton().disabled).toBeFalse();
    });
  });
});
