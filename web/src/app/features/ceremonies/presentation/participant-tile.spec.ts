import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { provideTestI18n } from '@testing/i18n';

import { ParticipantTile } from './participant-tile';
import { type ParticipantRow } from '../domain/participant-row';

const ANA: ParticipantRow = {
  identity: 'user-ana',
  name: 'Ana Gil',
  email: 'ana@example.test',
  connected: true,
  speaking: false,
  self: false,
};

@Component({
  imports: [ParticipantTile],
  template: `<agl-participant-tile [row]="row()" />`,
})
class Host {
  readonly row = signal(ANA);
}

describe('ParticipantTile', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideTestI18n()] });
  });

  async function render(row: ParticipantRow): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Host);
    fixture.componentInstance.row.set(row);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  function text(tile: HTMLElement, testId: string): string | undefined {
    return tile.querySelector(`[data-testid="${testId}"]`)?.textContent.replace(/\s+/g, ' ').trim();
  }

  it('shows the initials, the name, the email and that the person is connected', async () => {
    const tile = await render(ANA);

    expect(tile.textContent).toContain('AG');
    expect(text(tile, 'participant-name')).toBe('Ana Gil');
    expect(text(tile, 'participant-email')).toBe('ana@example.test');
    expect(text(tile, 'participant-presence')).toBe('Conectado');
    expect(tile.querySelector('[data-testid="participant-presence"] svg')).toBeNull();
    expect(tile.querySelector('[data-testid="participant-self"]')).toBeNull();
  });

  it('marks the row of the one looking at the screen', async () => {
    const tile = await render({ ...ANA, self: true });

    expect(text(tile, 'participant-self')).toBe('· tú');
  });

  it('says in words that a person is disconnected', async () => {
    const tile = await render({ ...ANA, connected: false });

    expect(text(tile, 'participant-presence')).toBe('Desconectado');
    expect(tile.querySelector('[data-testid="participant-presence"] svg')).not.toBeNull();
  });

  it('calls «Participante» someone the room does not know by name, with its initial', async () => {
    const tile = await render({ ...ANA, name: '', email: null });

    expect(text(tile, 'participant-name')).toBe('Participante');
    expect(tile.querySelector('[aria-hidden="true"]')?.textContent.trim()).toBe('P');
    expect(tile.querySelector('[data-testid="participant-email"]')).toBeNull();
  });

  it('shows no voice indicator while the person is silent', async () => {
    const tile = await render(ANA);

    expect(tile.querySelector('[data-testid="participant-speaking"]')).toBeNull();
    expect(tile.querySelector('agl-participant-tile > div')!.classList).not.toContain('ring-2');
  });

  it('marks who is speaking with a ring, an icon and «Hablando», not only with colour', async () => {
    const tile = await render({ ...ANA, speaking: true });

    const indicator = tile.querySelector('[data-testid="participant-speaking"]');
    expect(text(tile, 'participant-speaking')).toBe('Hablando');
    expect(indicator?.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true');
    expect(indicator?.querySelector('span')?.classList).toContain('sr-only');
    expect(indicator?.querySelector('span')?.classList).toContain('sm:not-sr-only');
    expect(tile.querySelector('agl-participant-tile > div')!.classList).toContain('ring-2');
    expect(tile.querySelector('agl-participant-tile > div')!.classList).toContain('ring-success');
  });

  it('leaves the email out when there is none', async () => {
    const tile = await render({ ...ANA, email: null });

    expect(tile.querySelector('[data-testid="participant-email"]')).toBeNull();
    expect(text(tile, 'participant-name')).toBe('Ana Gil');
  });
});
