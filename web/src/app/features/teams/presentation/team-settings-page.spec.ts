import { TestBed } from '@angular/core/testing';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { NEVER, of, Subject, throwError, type Observable } from 'rxjs';

import { ShellContext } from '@core/shell/shell-context';
import { provideTestI18n } from '@testing/i18n';
import { aTeam } from '@testing/team';
import { provideTestTenant } from '@testing/tenant';

import { TeamSettingsPage } from './team-settings-page';
import { TeamsPort } from '../application/teams.port';
import { UsersPort } from '../application/users.port';
import { MemberFailure } from '../domain/member-failure';
import { type Team } from '../domain/team';
import {
  type InvitationOutcome,
  type MemberInvitation,
  type MyMembership,
  type TeamMember,
  type TeamMembers,
  type TeamRole,
} from '../domain/team-member';

const ANA: TeamMember = {
  userId: 'ana',
  fullName: 'Ana Gil',
  email: 'ana@example.com',
  role: 'admin',
  label: 'admin',
  joinedAt: new Date('2026-10-08T15:04:05Z'),
  roleChangeBlockedBy: 'last_admin',
  removalBlockedBy: 'last_admin',
};
const BRUNO: TeamMember = {
  userId: 'bruno',
  fullName: 'Bruno Díaz',
  email: 'bruno@example.com',
  role: 'member',
  label: 'member',
  joinedAt: new Date('2026-10-08T15:04:05Z'),
  roleChangeBlockedBy: null,
  removalBlockedBy: null,
};

/** The team of the screen, read for the top bar. */
class FakeTeamsPort extends TeamsPort {
  dashboard(): Observable<never> {
    return NEVER;
  }

  listMine(): Observable<readonly Team[]> {
    return of([]);
  }

  create(): Observable<string> {
    return of('new');
  }

  get(teamId: string): Observable<Team> {
    return of(aTeam(teamId, 'Atlas'));
  }
}

/**
 * Port double: list() answers what `answer` holds for the team (a failure, or nothing yet for
 * 'slow'); the commands wait until the test answers them.
 */
class FakeUsersPort extends UsersPort {
  answer: TeamMembers | MemberFailure = {
    roles: [
      { role: 'admin', label: 'admin' },
      { role: 'member', label: 'member' },
    ],
    members: [ANA, BRUNO],
  };
  readonly listed: string[] = [];
  readonly invitations: MemberInvitation[] = [];
  readonly changes: [string, TeamRole][] = [];
  readonly removals: string[] = [];
  private pendingCommand = new Subject<void>();
  private pendingInvitation = new Subject<InvitationOutcome>();

  list(teamId: string): Observable<TeamMembers> {
    this.listed.push(teamId);
    if (teamId === 'slow') {
      return NEVER;
    }
    const answer = this.answer;
    return answer instanceof MemberFailure ? throwError(() => answer) : of(answer);
  }

  get(teamId: string, userId: string): Observable<TeamMember> {
    const answer = this.answer;
    const member =
      answer instanceof MemberFailure ? undefined : answer.members.find((m) => m.userId === userId);
    return member === undefined ? throwError(() => new MemberFailure('not_found')) : of(member);
  }

  /** How the API calls Ana in the team right now; each read of `me` is counted. */
  myLabel: MyMembership['label'] = 'scrum_master';
  meCalls = 0;

  me(): Observable<MyMembership> {
    this.meCalls += 1;
    return of({
      userId: 'ana',
      fullName: 'Ana Gil',
      email: 'ana@example.com',
      role: this.myLabel === 'member' ? 'member' : 'admin',
      label: this.myLabel,
      joinedAt: new Date('2026-10-08T15:04:05Z'),
    });
  }

  invite(teamId: string, invitation: MemberInvitation): Observable<InvitationOutcome> {
    this.invitations.push(invitation);
    this.pendingInvitation = new Subject<InvitationOutcome>();
    return this.pendingInvitation;
  }

  changeRole(teamId: string, userId: string, role: TeamRole): Observable<void> {
    this.changes.push([userId, role]);
    return this.command();
  }

  remove(teamId: string, userId: string): Observable<void> {
    this.removals.push(userId);
    return this.command();
  }

  /** The API accepts the pending change. */
  accept(): void {
    this.pendingCommand.next();
    this.pendingCommand.complete();
  }

  /** The API refuses the pending change. */
  refuse(failure: Error): void {
    this.pendingCommand.error(failure);
  }

  /** The API answers the pending invitation. */
  answerInvitation(outcome: InvitationOutcome): void {
    this.pendingInvitation.next(outcome);
    this.pendingInvitation.complete();
  }

  private command(): Observable<void> {
    this.pendingCommand = new Subject<void>();
    return this.pendingCommand;
  }
}

describe('TeamSettingsPage', () => {
  let port: FakeUsersPort;
  let harness: RouterTestingHarness;
  let page: HTMLElement;

  beforeEach(async () => {
    port = new FakeUsersPort();
    TestBed.configureTestingModule({
      providers: [
        provideTestI18n(),
        provideTestTenant(),
        provideRouter(
          [{ path: ':tenant/teams/:teamId/settings', component: TeamSettingsPage }],
          withComponentInputBinding(),
        ),
        { provide: UsersPort, useValue: port },
        { provide: TeamsPort, useClass: FakeTeamsPort },
      ],
    });
    harness = await RouterTestingHarness.create();
  });

  async function open(url = '/acme/teams/atlas/settings'): Promise<void> {
    await harness.navigateByUrl(url);
    await harness.fixture.whenStable();
    page = harness.routeNativeElement!;
  }

  /** Lets the page react to an answer the facade awaited (see CreateTeamPage's spec). */
  async function settled(): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve));
    await harness.fixture.whenStable();
  }

  function rows(): HTMLTableRowElement[] {
    return Array.from(page.querySelectorAll('tbody tr'));
  }

  function roleControl(userId: string): HTMLSelectElement {
    return page.querySelector<HTMLSelectElement>(`#member-role-${userId}`)!;
  }

  function button(text: string, scope: ParentNode = page): HTMLButtonElement {
    const found = Array.from(scope.querySelectorAll('button')).find(
      (candidate) => candidate.textContent.trim() === text,
    );
    expect(found).withContext(`a button "${text}"`).toBeDefined();
    return found!;
  }

  function removeButtonOf(name: string): HTMLButtonElement {
    return page.querySelector<HTMLButtonElement>(
      `button[aria-label="Eliminar a ${name} del equipo"]`,
    )!;
  }

  function dialog(): HTMLDialogElement | null {
    return page.querySelector('dialog');
  }

  function text(element: Element | null | undefined): string {
    return element?.textContent.replace(/\s+/g, ' ').trim() ?? '';
  }

  // ----------------------------------------------------------- criterion 1 --
  it('lists each member with name, email and the translated label of their role', async () => {
    await open();

    expect(port.listed).toEqual(['atlas']);
    expect(page.querySelector('h2')?.textContent.trim()).toBe('Equipo');
    const [ana, bruno] = rows();
    expect(text(ana)).toContain('Ana Gil');
    expect(text(ana)).toContain('ana@example.com');
    expect(text(ana)).toContain('Administrador');
    expect(text(bruno)).toContain('Bruno Díaz');
    expect(text(bruno)).toContain('bruno@example.com');
    expect(text(bruno)).toContain('Miembro');
  });

  it('is the Team tab of the settings, next to the Sprint one', async () => {
    await open();

    expect(page.querySelector('h1')?.textContent.trim()).toBe('Configuración');
    const tabs = Array.from(page.querySelectorAll('nav a'));
    expect(tabs.map((tab) => text(tab))).toEqual(['Equipo', 'Sprint']);
    expect(text(page.querySelector('nav a[aria-current="page"]'))).toBe('Equipo');
    expect(tabs[1]?.getAttribute('href')).toBe('/acme/teams/atlas/settings/sprint');
    // The end-to-end tests of HU-06 look for this title: it keeps its text.
    expect(text(page.querySelector('[data-testid="settings-title"]'))).toBe('Equipo');
  });

  it('shows each role in a control with the options the API gave', async () => {
    await open();

    const control = roleControl('bruno');
    expect(control.value).toBe('member');
    expect(Array.from(control.options).map((option) => option.text.trim())).toEqual([
      'Administrador',
      'Miembro',
    ]);
    expect(page.querySelector('label[for="member-role-bruno"]')?.textContent.trim()).toBe(
      'Rol de Bruno Díaz',
    );
  });

  it('says it is loading while the API has not answered', async () => {
    await harness.navigateByUrl('/acme/teams/slow/settings');
    TestBed.tick();
    page = harness.routeNativeElement!;

    expect(text(page.querySelector('[role="status"]'))).toBe('Cargando a los integrantes…');
    expect(rows()).toEqual([]);
  });

  // ----------------------------------------------------------- criterion 3 --
  it('disables the role of a member with the reason the API gives, tied to the control', async () => {
    port.answer = {
      roles: [
        { role: 'admin', label: 'admin' },
        { role: 'member', label: 'member' },
      ],
      members: [
        { ...ANA, roleChangeBlockedBy: 'sprint_in_progress' },
        { ...BRUNO, roleChangeBlockedBy: 'sprint_in_progress' },
      ],
    };
    await open();

    const control = roleControl('bruno');
    expect(control.disabled).toBeTrue();
    const reason = page.querySelector(`#${control.getAttribute('aria-describedby')!}`);
    expect(text(reason)).toBe(
      'No se puede cambiar el rol mientras el equipo tiene un sprint activo.',
    );
  });

  it('leaves the role of a member enabled, without a reason, when nothing blocks it', async () => {
    await open();

    expect(roleControl('bruno').disabled).toBeFalse();
    expect(roleControl('bruno').hasAttribute('aria-describedby')).toBeFalse();
    expect(roleControl('ana').disabled).toBeTrue();
    expect(text(page.querySelector('#member-role-blocked-ana'))).toBe(
      'Es el único Administrador: el equipo no puede quedarse sin Administrador.',
    );
  });

  it('changes the role of a member and asks the API for the list again', async () => {
    await open();

    roleControl('bruno').value = 'admin';
    roleControl('bruno').dispatchEvent(new Event('change'));
    await harness.fixture.whenStable();
    expect(text(page.querySelector('[role="status"]'))).toBe('Guardando…');
    expect(roleControl('bruno').disabled).toBeTrue();
    port.accept();
    await settled();

    expect(port.changes).toEqual([['bruno', 'admin']]);
    expect(port.listed).toEqual(['atlas', 'atlas']);
    expect(page.querySelector('[role="alert"]')).toBeNull();
  });

  it('puts the role back and says why when the API refuses the change', async () => {
    await open();

    roleControl('bruno').value = 'admin';
    roleControl('bruno').dispatchEvent(new Event('change'));
    port.refuse(new MemberFailure('sprint_in_progress'));
    await settled();

    expect(roleControl('bruno').value).toBe('member');
    expect(text(page.querySelector('[role="alert"]'))).toBe(
      'No se puede cambiar el rol mientras el equipo tiene un sprint activo.',
    );
    expect(port.listed).toEqual(['atlas', 'atlas']);
  });

  // ----------------------------------------------------------- criterion 4 --
  it('asks for confirmation before removing, warning about the calls of the team', async () => {
    await open();

    removeButtonOf('Bruno Díaz').click();
    await harness.fixture.whenStable();

    const confirmation = dialog();
    expect(confirmation?.open).toBeTrue();
    expect(text(confirmation?.querySelector('h2'))).toBe('¿Eliminar a Bruno Díaz del equipo?');
    expect(text(confirmation)).toContain(
      'Bruno Díaz dejará de pertenecer al equipo y de recibir sus convocatorias.',
    );
    expect(text(confirmation)).toContain('Su cuenta de Agilina no se borra');
    expect(port.removals).toEqual([]);
  });

  it('removes the member once confirmed and closes the confirmation', async () => {
    await open();
    removeButtonOf('Bruno Díaz').click();
    await harness.fixture.whenStable();

    button('Eliminar del equipo', dialog()!).click();
    port.answer = { roles: [], members: [ANA] };
    port.accept();
    await settled();

    expect(port.removals).toEqual(['bruno']);
    expect(dialog()).toBeNull();
    expect(rows().map((row) => text(row))).not.toContain(jasmine.stringContaining('Bruno'));
  });

  it('does not remove anybody when the confirmation is cancelled', async () => {
    await open();
    removeButtonOf('Bruno Díaz').click();
    await harness.fixture.whenStable();

    button('Cancelar', dialog()!).click();
    await harness.fixture.whenStable();

    expect(dialog()).toBeNull();
    expect(port.removals).toEqual([]);
  });

  it('keeps the confirmation open and says why when the API refuses the removal', async () => {
    await open();
    removeButtonOf('Bruno Díaz').click();
    await harness.fixture.whenStable();

    button('Eliminar del equipo', dialog()!).click();
    port.refuse(new MemberFailure('not_found'));
    await settled();

    expect(dialog()?.open).toBeTrue();
    expect(text(dialog()?.querySelector('[role="alert"]'))).toBe(
      'Esta persona ya no está en el equipo.',
    );
  });

  // ----------------------------------------------------------- criterion 5 --
  it('does not let the only admin be removed and says why', async () => {
    await open();

    const remove = removeButtonOf('Ana Gil');
    expect(remove.disabled).toBeTrue();
    expect(text(page.querySelector(`#${remove.getAttribute('aria-describedby')!}`))).toBe(
      'Es el único Administrador: no se puede eliminar del equipo.',
    );
    expect(removeButtonOf('Bruno Díaz').disabled).toBeFalse();
  });

  // ----------------------------------------------------------- criterion 2 --
  it('invites a member and tells what the API did', async () => {
    await open();

    button('Invitar miembro').click();
    await harness.fixture.whenStable();
    const form = dialog()!;
    const name = form.querySelector<HTMLInputElement>('#invite-full-name')!;
    const email = form.querySelector<HTMLInputElement>('#invite-email')!;
    name.value = 'Laura';
    name.dispatchEvent(new Event('input'));
    email.value = 'laura@example.com';
    email.dispatchEvent(new Event('input'));
    await harness.fixture.whenStable();
    button('Enviar invitación', form).click();
    port.answerInvitation('invitation_sent');
    await settled();

    expect(port.invitations).toEqual([
      { fullName: 'Laura', email: 'laura@example.com', role: 'member' },
    ]);
    expect(dialog()).toBeNull();
    expect(text(page.querySelector('[role="status"]'))).toBe(
      'Enviamos la invitación por correo. El enlace de activación vale 7 días.',
    );
    expect(port.listed).toEqual(['atlas', 'atlas']);
  });

  // ----------------------------------------------------------- criterion 6 --
  it('shows "no access" when the API refuses the screen to this user', async () => {
    port.answer = new MemberFailure('forbidden');
    await open();

    expect(page.querySelector('h1')?.textContent.trim()).toBe('No tienes acceso a esta pantalla');
    expect(text(page)).toContain(
      'Solo quienes administran el equipo pueden gestionar a sus integrantes.',
    );
    expect(rows()).toEqual([]);
    expect(page.querySelector('select')).toBeNull();
    expect(page.querySelector('a[href="/acme/teams/atlas"]')).not.toBeNull();
  });

  it('says the admin lost the access by their own role change, and leads back to the team', async () => {
    port.answer = {
      ...(port.answer as TeamMembers),
      members: [{ ...ANA, roleChangeBlockedBy: null }, BRUNO],
    };
    await open();

    roleControl('ana').value = 'member';
    roleControl('ana').dispatchEvent(new Event('change'));
    port.answer = new MemberFailure('forbidden');
    port.accept();
    await settled();

    expect(page.querySelector('h1')?.textContent.trim()).toBe('Ya no administras este equipo');
    expect(text(page)).toContain('Tu cambio quedó guardado: ahora eres Miembro');
    expect(page.querySelector('a[href="/acme/teams/atlas"]')).not.toBeNull();
  });

  it('says the admin left the team by their own removal, and leads to their teams', async () => {
    port.answer = {
      ...(port.answer as TeamMembers),
      members: [{ ...ANA, removalBlockedBy: null }, BRUNO],
    };
    await open();

    removeButtonOf('Ana Gil').click();
    await harness.fixture.whenStable();
    button('Eliminar del equipo', dialog()!).click();
    port.answer = new MemberFailure('forbidden');
    port.accept();
    await settled();

    expect(page.querySelector('h1')?.textContent.trim()).toBe('Ya no administras este equipo');
    expect(text(page)).toContain('ya no perteneces a este equipo');
    expect(page.querySelector('a[href="/acme/teams"]')).not.toBeNull();
  });

  it('asks to sign in again when the API does not recognise the session', async () => {
    port.answer = new MemberFailure('not_authenticated');
    await open();

    expect(text(page.querySelector('[role="alert"]'))).toBe(
      'Tu sesión no es válida o expiró. Inicia sesión de nuevo.',
    );
    expect(rows()).toEqual([]);
  });

  it('shows a generic message when the list cannot be loaded for another reason', async () => {
    port.answer = new MemberFailure('unavailable');
    await open();

    expect(text(page.querySelector('[role="alert"]'))).toBe(
      'No se pudo cargar a los integrantes. Inténtalo de nuevo más tarde.',
    );
    expect(page.querySelector('h2')?.textContent.trim()).toBe('Equipo');
  });

  it('puts the team and how the user is called in it in the top bar while it lives', async () => {
    await open();

    expect(TestBed.inject(ShellContext).team()).toEqual({
      id: 'atlas',
      name: 'Atlas',
      roleLabel: 'scrum_master',
      userName: 'Ana Gil',
      canConfigure: true,
    });
  });

  it('names whoever manages the team with the label of the team in its messages', async () => {
    port.answer = {
      roles: [
        { role: 'admin', label: 'admin' },
        { role: 'member', label: 'member' },
      ],
      members: [{ ...ANA, label: 'admin' }, BRUNO],
    };

    await open();

    expect(page.querySelector('[data-testid=member-role-blocked]')?.textContent).toContain(
      'Es el único Administrador',
    );
  });

  it('has an eye per member that opens their detail in a dialog, next to the way to remove', async () => {
    await open();
    const eye = page.querySelector<HTMLButtonElement>(
      '[data-testid="member-bruno@example.com"] [data-testid=member-view]',
    )!;

    expect(eye.getAttribute('aria-label')).toBe('Ver a Bruno Díaz');
    eye.click();
    await harness.fixture.whenStable();

    expect(page.querySelector('[data-testid=user-detail-title]')?.textContent.trim()).toBe(
      'Bruno Díaz',
    );
    expect(page.querySelector('[data-testid=user-detail-email]')?.textContent.trim()).toBe(
      'bruno@example.com',
    );
  });

  it('closes the detail and leaves the list as it was', async () => {
    await open();
    page.querySelector<HTMLButtonElement>('[data-testid=member-view]')!.click();
    await harness.fixture.whenStable();

    page.querySelector<HTMLButtonElement>('[data-testid=user-detail-close]')!.click();
    await harness.fixture.whenStable();

    expect(page.querySelector('[data-testid=user-detail-title]')).toBeNull();
    expect(rows().length).toBe(2);
  });

  it('asks the API for me again after a role change, so the top bar shows my label of now', async () => {
    await open();
    const shell = TestBed.inject(ShellContext);
    expect(shell.team()?.roleLabel).toBe('scrum_master');
    expect(port.meCalls).toBe(1);

    // As if the change had been Ana's own: the API now calls her a member.
    port.myLabel = 'member';
    roleControl('bruno').value = 'admin';
    roleControl('bruno').dispatchEvent(new Event('change'));
    await harness.fixture.whenStable();
    port.accept();
    await settled();

    expect(port.meCalls).toBe(2);
    expect(shell.team()?.roleLabel).toBe('member');
  });

  it('asks the API for me again after a removal', async () => {
    await open();
    removeButtonOf('Bruno Díaz').click();
    await harness.fixture.whenStable();

    button('Eliminar del equipo', dialog()!).click();
    port.accept();
    await settled();

    expect(port.meCalls).toBe(2);
  });

  it('shows the eye and the bin as icon buttons, the bin dimmed when the removal is blocked', async () => {
    await open();
    const ana = page.querySelector('[data-testid="member-ana@example.com"]')!;
    const bruno = page.querySelector('[data-testid="member-bruno@example.com"]')!;

    for (const id of ['member-view', 'member-remove']) {
      expect(bruno.querySelector(`[data-testid=${id}]`)?.classList).toContain('size-9');
    }
    const blocked = ana.querySelector<HTMLButtonElement>('[data-testid=member-remove]')!;
    expect(blocked.disabled).toBeTrue();
    expect(blocked.classList).toContain('disabled:opacity-40');
  });
});
