import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { AgilinaAvatar } from './agilina-avatar';

@Component({
  imports: [AgilinaAvatar],
  template: `<agl-agilina-avatar [speaking]="speaking()" [present]="present()" />`,
})
class Host {
  readonly speaking = signal(false);
  readonly present = signal(true);
}

describe('AgilinaAvatar', () => {
  async function render(speaking: boolean, present: boolean): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(Host);
    fixture.componentInstance.speaking.set(speaking);
    fixture.componentInstance.present.set(present);
    await fixture.whenStable();
    return (fixture.nativeElement as HTMLElement).querySelector('agl-agilina-avatar')!;
  }

  it('only decorates: the card says in words where Agilina is and whether she speaks', async () => {
    const avatar = await render(false, true);

    expect(avatar.getAttribute('aria-hidden')).toBe('true');
    expect(avatar.querySelector('svg')).not.toBeNull();
  });

  it('is at rest, in the room, while she is silent', async () => {
    const avatar = await render(false, true);

    expect(avatar.classList).not.toContain('speaking');
    expect(avatar.classList).not.toContain('absent');
  });

  it('talks while she speaks', async () => {
    const avatar = await render(true, true);

    expect(avatar.classList).toContain('speaking');
  });

  it('is greyed out while she is not in the room', async () => {
    const avatar = await render(false, false);

    expect(avatar.classList).toContain('absent');
  });
});
