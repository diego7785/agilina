import { Location } from '@angular/common';
import { ApplicationRef, Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ShellContext } from '@core/shell/shell-context';
import { provideTestI18n } from '@testing/i18n';
import { provideTestTenant } from '@testing/tenant';

import { Header } from './header';

@Component({ template: '' })
class Screen {}

/** The team of the top bar, with what the tests do not care about filled in. */
function aShellTeam(
  changes: Partial<{
    id: string;
    name: string;
    roleLabel: string;
    userName: string;
    canConfigure: boolean;
  }> = {},
) {
  return {
    id: 'atlas',
    name: 'Atlas',
    roleLabel: 'scrum_master',
    userName: 'Ana Gil',
    canConfigure: true,
    ...changes,
  };
}

describe('Header', () => {
  async function render(team?: ReturnType<typeof aShellTeam>): Promise<HTMLElement> {
    TestBed.configureTestingModule({
      imports: [Header],
      providers: [
        provideTestI18n(),
        provideTestTenant(),
        provideRouter([
          { path: ':tenant/teams', component: Screen },
          { path: ':tenant/teams/:teamId', component: Screen },
          { path: ':tenant/teams/:teamId/settings', component: Screen },
        ]),
      ],
    });
    if (team !== undefined) {
      TestBed.inject(ShellContext).enter(team);
    }
    const fixture = TestBed.createComponent(Header);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the brand and the tagline in the active language', async () => {
    const element = await render();

    expect(element.textContent).toContain('Agilina');
    expect(element.textContent).toContain('Scrum Master virtual para la reunión diaria');
  });

  it('inside a team shows its name and the label of the role of the user in it', async () => {
    const element = await render(aShellTeam({ userName: 'Ana María Gil' }));

    expect(element.querySelector('[data-testid=header-team]')?.textContent).toBe('Atlas');
    expect(element.querySelector('[data-testid=header-role-label]')?.textContent.trim()).toBe(
      'Scrum Master',
    );
    expect(element.textContent).not.toContain('reunión diaria');
  });

  it('shows the name of the person and their initials next to the team', async () => {
    const element = await render(aShellTeam({ userName: 'ana maría gil ruiz' }));

    expect(element.querySelector('[data-testid=header-user-name]')?.textContent.trim()).toBe(
      'ana maría gil ruiz',
    );
    expect(element.querySelector('[data-testid=header-user-initials]')?.textContent.trim()).toBe(
      'AM',
    );
  });

  it('shows no person outside a team', async () => {
    const element = await render();

    expect(element.querySelector('[data-testid=header-user]')).toBeNull();
  });

  it('calls the same admin Administrador once the team is autonomous', async () => {
    const element = await render(aShellTeam({ name: 'Nova', roleLabel: 'admin' }));

    expect(element.querySelector('[data-testid=header-role-label]')?.textContent.trim()).toBe(
      'Administrador',
    );
  });

  describe('the way to another team', () => {
    it('offers to switch team inside a team, to the selector', async () => {
      const element = await render(aShellTeam());

      const link = element.querySelector('[data-testid=change-team]');
      expect(link?.textContent.trim()).toBe('Cambiar de equipo');
      expect(link?.getAttribute('href')).toBe('/acme/teams');
    });

    it('asks the selector to list the teams even if the person has only one', async () => {
      const element = await render(aShellTeam());

      element.querySelector<HTMLAnchorElement>('[data-testid=change-team]')!.click();
      await TestBed.inject(ApplicationRef).whenStable();

      expect(TestBed.inject(Location).getState()).toEqual(
        jasmine.objectContaining({ choose: true }),
      );
    });

    it('offers nothing outside a team', async () => {
      const element = await render();

      expect(element.querySelector('[data-testid=change-team]')).toBeNull();
    });
  });

  describe('the entries of the team', () => {
    it('shows the dashboard and, to an admin, the settings, each with its own address', async () => {
      const element = await render(aShellTeam({ canConfigure: true }));

      const nav = element.querySelector('nav');
      expect(nav?.getAttribute('aria-label')).toBe('Navegación del equipo');
      expect(element.querySelector('[data-testid=nav-dashboard]')?.getAttribute('href')).toBe(
        '/acme/teams/atlas',
      );
      expect(element.querySelector('[data-testid=nav-settings]')?.getAttribute('href')).toBe(
        '/acme/teams/atlas/settings',
      );
      expect(element.querySelector('[data-testid=nav-settings]')?.textContent.trim()).toBe(
        'Configuración',
      );
    });

    it('does not even render the settings entry for who cannot configure the team', async () => {
      const element = await render(aShellTeam({ canConfigure: false, roleLabel: 'member' }));

      expect(element.querySelector('[data-testid=nav-dashboard]')).not.toBeNull();
      expect(element.querySelector('[data-testid=nav-settings]')).toBeNull();
      expect(element.textContent).not.toContain('Configuración');
    });

    it('shows no entries outside a team', async () => {
      const element = await render();

      expect(element.querySelector('nav')).toBeNull();
    });
  });
});
