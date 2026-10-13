import { TestBed } from '@angular/core/testing';
import { TranslocoService } from '@jsverse/transloco';

import { provideTestI18n } from '@testing/i18n';

import { MAX_NOTIFICATIONS, Notifier, SUCCESS_DURATION_MS } from './notifier';

describe('Notifier', () => {
  let notifier: Notifier;

  beforeEach(() => {
    jasmine.clock().install();
    TestBed.configureTestingModule({ providers: [provideTestI18n()] });
    notifier = TestBed.inject(Notifier);
  });

  afterEach(() => {
    jasmine.clock().uninstall();
  });

  function messages(): string[] {
    return notifier.notifications().map((notice) => notice.message);
  }

  it('starts with nothing to say', () => {
    expect(notifier.notifications()).toEqual([]);
  });

  it('shows a success in the language of the person, from the key of its text', () => {
    notifier.success('teams.sprint.saved');

    expect(notifier.notifications()).toEqual([
      { id: jasmine.any(Number), kind: 'success', message: 'Sprint guardado.' },
    ]);
  });

  it('translates with the parameters it is given', () => {
    notifier.success('teams.settings.role_of', { name: 'Ana Gil' });

    expect(messages()).toEqual(['Rol de Ana Gil']);
  });

  it('follows the active language', () => {
    TestBed.inject(TranslocoService).setActiveLang('en');

    notifier.success('teams.sprint.saved');

    expect(messages()).toEqual(['Sprint saved.']);
  });

  it('shows an error as an error', () => {
    notifier.error('teams.sprint.save.failed');

    expect(notifier.notifications()[0]?.kind).toBe('error');
    expect(messages()).toEqual(['No se pudo guardar el sprint. Inténtalo de nuevo.']);
  });

  it('gives each notice its own id', () => {
    notifier.success('teams.sprint.saved');
    notifier.success('teams.sprint.saved');

    const [first, second] = notifier.notifications();
    expect(first?.id).not.toBe(second?.id);
  });

  describe('a success', () => {
    it('goes away by itself after five seconds', () => {
      notifier.success('teams.sprint.saved');

      jasmine.clock().tick(SUCCESS_DURATION_MS - 1);
      expect(notifier.notifications().length).toBe(1);

      jasmine.clock().tick(1);
      expect(notifier.notifications()).toEqual([]);
    });

    it('does not go away while it is paused, and counts again once resumed', () => {
      notifier.success('teams.sprint.saved');
      const id = notifier.notifications()[0]!.id;

      notifier.pause(id);
      jasmine.clock().tick(SUCCESS_DURATION_MS * 3);
      expect(notifier.notifications().length).toBe(1);

      notifier.resume(id);
      jasmine.clock().tick(SUCCESS_DURATION_MS);
      expect(notifier.notifications()).toEqual([]);
    });

    it('closes when the person closes it, and its time does nothing afterwards', () => {
      notifier.success('teams.sprint.saved');
      notifier.success('teams.sprint.saved');
      const [first, second] = notifier.notifications();

      notifier.dismiss(first!.id);
      expect(notifier.notifications()).toEqual([second!]);

      jasmine.clock().tick(SUCCESS_DURATION_MS);
      expect(notifier.notifications()).toEqual([]);
    });
  });

  describe('an error', () => {
    it('stays until it is closed', () => {
      notifier.error('teams.sprint.save.failed');

      jasmine.clock().tick(SUCCESS_DURATION_MS * 10);

      expect(notifier.notifications().length).toBe(1);
    });

    it('does not start a timer when the person moves away from it', () => {
      notifier.error('teams.sprint.save.failed');
      const id = notifier.notifications()[0]!.id;

      notifier.pause(id);
      notifier.resume(id);
      jasmine.clock().tick(SUCCESS_DURATION_MS * 10);

      expect(notifier.notifications().length).toBe(1);
    });

    it('closes when the person closes it', () => {
      notifier.error('teams.sprint.save.failed');

      notifier.dismiss(notifier.notifications()[0]!.id);

      expect(notifier.notifications()).toEqual([]);
    });
  });

  describe('many at once', () => {
    it('shows at most three: a new one pushes out the oldest', () => {
      for (const name of ['Ana', 'Bruno', 'Carla', 'Dani']) {
        notifier.success('teams.settings.role_of', { name });
      }

      expect(MAX_NOTIFICATIONS).toBe(3);
      expect(messages()).toEqual([
        'Rol de Bruno',
        'Rol de Carla',
        'Rol de Dani',
      ]);
    });

    it('leaves no timer behind for the one that was pushed out', () => {
      for (let count = 0; count < 4; count++) {
        notifier.success('teams.sprint.saved');
      }
      const pushedOut = 1;
      expect(notifier.notifications().some((notice) => notice.id === pushedOut)).toBeFalse();

      jasmine.clock().tick(SUCCESS_DURATION_MS);

      expect(notifier.notifications()).toEqual([]);
    });
  });

  it('ignores pausing or closing a notice that is already gone', () => {
    notifier.pause(99);
    notifier.resume(99);
    notifier.dismiss(99);

    expect(notifier.notifications()).toEqual([]);
  });
});
