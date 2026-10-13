import { Component, computed, inject, input, type OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoPipe, TranslocoService } from '@jsverse/transloco';

import { Notifier } from '@core/notifications/notifier';
import { TenantContext } from '@core/tenant/tenant-context';
import { Button } from '@shared/ui/button';
import { IconButton } from '@shared/ui/icon-button';
import { Select } from '@shared/ui/select';

import { InviteMemberDialog } from './invite-member-dialog';
import { problemMessageKey } from './problem-message';
import { RemoveMemberDialog } from './remove-member-dialog';
import { SettingsNoAccess } from './settings-no-access';
import { SettingsTabs } from './settings-tabs';
import { UserDetailDialog } from './user-detail-dialog';
import { TeamMembersFacade } from '../application/team-members.facade';
import { TeamShellFacade } from '../application/team-shell.facade';
import { adminLabelOf } from '../domain/admin-label';
import { type InvitationOutcome, type TeamMember } from '../domain/team-member';

/**
 * Settings → Team: the members of the team with their name, email and role, and what an admin
 * does with them (invite, change a role, remove). The screen does not decide who may open it
 * nor what may change: it shows what the API answers, disables what the API marks as blocked
 * with the API's reason, and shows "no access" when the API refuses the team. When that refusal
 * follows a change made here (an admin demoted or removed themself), it says so instead.
 */
@Component({
  selector: 'agl-team-settings-page',
  imports: [
    RouterLink,
    TranslocoDirective,
    TranslocoPipe,
    Button,
    IconButton,
    Select,
    InviteMemberDialog,
    RemoveMemberDialog,
    SettingsNoAccess,
    SettingsTabs,
    UserDetailDialog,
  ],
  providers: [TeamMembersFacade, TeamShellFacade],
  templateUrl: './team-settings-page.html',
})
export class TeamSettingsPage implements OnInit {
  /** The :teamId of the route, bound by the router (withComponentInputBinding). */
  readonly teamId = input.required<string>();

  private readonly facade = inject(TeamMembersFacade);
  private readonly shell = inject(TeamShellFacade);
  private readonly notifier = inject(Notifier);
  private readonly transloco = inject(TranslocoService);
  protected readonly tenant = inject(TenantContext);

  protected readonly members = this.facade.members;
  protected readonly roles = this.facade.roles;
  /** How this team calls whoever manages it, for the messages that name that person. */
  protected readonly adminLabel = computed(() => adminLabelOf(this.roles()));
  protected readonly loading = this.facade.loading;
  protected readonly saving = this.facade.saving;
  protected readonly savingMember = this.facade.savingMember;
  /** The API refused the team to this user: not an admin of it, or not a member at all. */
  protected readonly forbidden = computed(() => this.facade.problem() === 'forbidden');
  /** The last change saved here, if any: a refusal after it means it took the access away. */
  private readonly lastChange = signal<'role_change' | 'removal' | null>(null);
  protected readonly lostAccess = computed(() => (this.forbidden() ? this.lastChange() : null));
  protected readonly problemMessage = computed(() =>
    this.forbidden() ? null : problemMessageKey(this.facade.problem()),
  );
  protected readonly removalMessage = computed(() =>
    problemMessageKey(this.facade.removalProblem()),
  );

  protected readonly inviting = signal(false);
  protected readonly removing = signal<TeamMember | null>(null);
  protected readonly viewing = signal<TeamMember | null>(null);

  ngOnInit(): void {
    this.facade.follow(this.teamId);
    this.shell.follow(this.teamId);
  }

  /**
   * Why a member's role is blocked, when the screen says it under the control. A sprint in
   * progress blocks everybody's role and the table already says so once, in its hint; saying it
   * under every role only repeats it. Being the last admin is about that person, so it stays.
   */
  protected roleNoteOf(member: TeamMember): 'last_admin' | null {
    return member.roleChangeBlockedBy === 'last_admin' ? 'last_admin' : null;
  }

  protected openInvitation(): void {
    this.inviting.set(true);
  }

  protected invited(outcome: InvitationOutcome): void {
    this.inviting.set(false);
    this.notifier.success(`teams.settings.invite.outcomes.${outcome}`);
    this.facade.reload();
  }

  protected async changeRole(member: TeamMember, control: HTMLSelectElement): Promise<void> {
    const role = this.roles().find((option) => option.role === control.value)?.role;
    if (role === undefined || role === member.role) {
      return;
    }
    const changed = await this.facade.changeRole(member.userId, role);
    if (changed) {
      this.lastChange.set('role_change');
      this.notifier.success('teams.settings.role_change.success', { name: member.fullName });
      // It may have been my own role: the top bar shows the one the API has now.
      this.shell.refresh();
    } else {
      // The API kept the old role: the control shows it again, and a notice says why.
      control.value = member.role;
      this.notifier.error(`teams.settings.role_change.${this.roleChangeKey()}`, {
        admin: this.transloco.translate(`app.role_labels.${this.adminLabel()}`),
      });
    }
  }

  protected askToRemove(member: TeamMember): void {
    this.facade.clearRemovalProblem();
    this.removing.set(member);
  }

  protected cancelRemoval(): void {
    this.removing.set(null);
    this.facade.clearRemovalProblem();
  }

  protected async confirmRemoval(): Promise<void> {
    const member = this.removing();
    if (member === null) {
      return;
    }
    if (await this.facade.remove(member.userId)) {
      this.lastChange.set('removal');
      this.removing.set(null);
      this.notifier.success('teams.settings.remove.success', { name: member.fullName });
      this.shell.refresh();
    }
  }

  /** The key, inside `teams.settings.role_change`, of why the API refused the new role. */
  private roleChangeKey(): string {
    return problemMessageKey(this.facade.roleChangeProblem()) ?? 'failed';
  }
}
