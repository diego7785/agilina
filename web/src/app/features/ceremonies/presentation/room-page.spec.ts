import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, withComponentInputBinding } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { provideTestI18n } from '@testing/i18n';
import {
  aDailyParticipant,
  aPresence,
  FakeDailyParticipantsPort,
  FakeRoomAccessPort,
  FakeRoomPort,
} from '@testing/room';
import { provideTestTenant } from '@testing/tenant';

import { RoomPage } from './room-page';
import { DailyParticipantsPort } from '../application/daily-participants.port';
import { RoomAccessPort } from '../application/room-access.port';
import { RoomPort } from '../application/room.port';
import { RoomFailure } from '../domain/room-failure';

describe('RoomPage', () => {
  let access: FakeRoomAccessPort;
  let room: FakeRoomPort;
  let invited: FakeDailyParticipantsPort;
  let harness: RouterTestingHarness;

  beforeEach(async () => {
    access = new FakeRoomAccessPort();
    room = new FakeRoomPort();
    invited = new FakeDailyParticipantsPort();
    TestBed.configureTestingModule({
      providers: [
        provideTestI18n(),
        provideTestTenant(),
        provideRouter(
          [
            { path: ':tenant/teams/:teamId/room', component: RoomPage },
            { path: ':tenant/teams/:teamId', children: [] },
          ],
          withComponentInputBinding(),
        ),
        { provide: DailyParticipantsPort, useValue: invited },
        { provide: RoomAccessPort, useValue: access },
        { provide: RoomPort, useValue: room },
      ],
    });
    harness = await RouterTestingHarness.create();
  });

  async function settle(): Promise<void> {
    for (let round = 0; round < 10; round++) {
      await Promise.resolve();
    }
    await harness.fixture.whenStable();
  }

  async function open(): Promise<HTMLElement> {
    await harness.navigateByUrl('/acme/teams/atlas/room');
    await settle();
    return harness.routeNativeElement!;
  }

  function text(page: HTMLElement, testId: string): string | undefined {
    return page.querySelector(`[data-testid="${testId}"]`)?.textContent.replace(/\s+/g, ' ').trim();
  }

  function click(page: HTMLElement, testId: string): void {
    page.querySelector<HTMLElement>(`[data-testid="${testId}"]`)!.click();
  }

  // -------------------------------------------- criteria 1 and 2: entering the room --
  describe('entering', () => {
    it('enters the room of the team of the address and says it is connected', async () => {
      const page = await open();

      expect(access.requested).toEqual(['atlas']);
      expect(page.querySelector('h1')?.textContent.trim()).toBe('Sala de reunión');
      expect(text(page, 'room-status')).toBe('Conectado');
      expect(page.querySelector('[data-testid="room-status"]')?.getAttribute('role')).toBe(
        'status',
      );
    });

    it('turns the microphone on as it enters', async () => {
      const page = await open();

      expect(room.microphonePrompts).toBe(1);
      expect(room.microphoneRequests).toBe(1);
      expect(text(page, 'microphone-on')).toBe('Micrófono activo');
      expect(page.querySelector('[data-testid="microphone-alert"]')).toBeNull();
    });

    it('says it is connecting while the room has not answered', async () => {
      room.connect = () => new Promise<void>(() => undefined);

      const page = await open();

      expect(text(page, 'room-status')).toBe('Conectando…');
      expect(page.querySelector('[data-testid="microphone-pending"]')).toBeNull();
    });
  });

  // -------------------------------------------- criterion 4: the microphone denied --
  describe('the microphone', () => {
    it('explains how to allow it when it is denied, and keeps the person as a listener', async () => {
      room.microphoneAnswer = 'denied';

      const page = await open();

      const alert = page.querySelector('[data-testid="microphone-alert"]');
      expect(alert?.getAttribute('role')).toBe('alert');
      expect(alert?.textContent).toContain('No tenemos permiso para usar tu micrófono');
      expect(text(page, 'microphone-help')).toContain('permite el micrófono para este sitio');
      expect(alert?.textContent).toContain('estás en la sala como oyente');
      expect(text(page, 'room-status')).toBe('Conectado');
    });

    it('asks for it again from the alert', async () => {
      room.microphoneAnswer = 'denied';
      const page = await open();

      room.microphoneAnswer = 'on';
      click(page, 'microphone-retry');
      await settle();

      expect(room.microphoneRequests).toBe(1);
      expect(text(page, 'microphone-on')).toBe('Micrófono activo');
    });

    it('says when there is no microphone', async () => {
      room.microphoneAnswer = 'not_found';

      const page = await open();

      expect(text(page, 'microphone-alert')).toContain('No encontramos un micrófono');
    });

    it('says when the microphone is busy', async () => {
      room.microphoneAnswer = 'unavailable';

      const page = await open();

      expect(text(page, 'microphone-alert')).toContain('Tu micrófono no está disponible');
    });

    it('says the microphone needs HTTPS, without a retry that cannot help', async () => {
      room.microphoneAnswer = 'insecure_context';

      const page = await open();

      expect(text(page, 'microphone-alert')).toContain('necesita una conexión segura');
      expect(text(page, 'microphone-help')).toContain('https://');
      expect(page.querySelector('[data-testid="microphone-retry"]')).toBeNull();
    });
  });

  // -------------------------------------------- criterion 5: the connection drops --
  describe('the connection', () => {
    it('says it is reconnecting while the network is down, and connected when it is back', async () => {
      const page = await open();

      room.emit({ kind: 'reconnecting' });
      await settle();
      expect(text(page, 'room-status')).toBe('Reconectando…');

      room.emit({ kind: 'reconnected' });
      await settle();
      expect(text(page, 'room-status')).toBe('Conectado');
    });

    it('offers to try again or go back when it could not get back', async () => {
      const page = await open();

      room.emit({ kind: 'lost' });
      await settle();

      expect(text(page, 'room-status')).toBe('Desconectado');
      expect(text(page, 'room-failure-message')).toBe(
        'Perdimos la conexión con la sala y no pudimos recuperarla.',
      );
      expect(text(page, 'room-retry')).toBe('Reintentar');
      expect(page.querySelector('[data-testid="room-back"]')?.getAttribute('href')).toBe(
        '/acme/teams/atlas',
      );
      expect(page.querySelector('[data-testid="microphone-on"]')).toBeNull();
    });

    it('enters again when retried', async () => {
      const page = await open();
      room.emit({ kind: 'lost' });
      await settle();

      click(page, 'room-retry');
      await settle();

      expect(access.requested.length).toBe(2);
      expect(text(page, 'room-status')).toBe('Conectado');
      expect(page.querySelector('[data-testid="room-failure"]')).toBeNull();
    });

    it('goes back to the dashboard', async () => {
      const page = await open();
      room.emit({ kind: 'lost' });
      await settle();

      click(page, 'room-back');
      await settle();

      expect(TestBed.inject(Router).url).toBe('/acme/teams/atlas');
    });

    it('leaves the room when the page goes away', async () => {
      await open();
      const before = room.disconnects;

      await harness.navigateByUrl('/acme/teams/atlas');

      expect(room.disconnects).toBe(before + 1);
    });
  });

  // ------------------------------------------------ the answers of the token (AGI-59) --
  describe('when it cannot enter', () => {
    it('says the person has no access, and only offers to go back', async () => {
      access.failure = new RoomFailure('no_access');

      const page = await open();

      expect(text(page, 'room-failure-message')).toBe('No tienes acceso a esta sala.');
      expect(page.querySelector('[data-testid="room-retry"]')).toBeNull();
      expect(page.querySelector('[data-testid="room-back"]')).not.toBeNull();
    });

    it('says the team has no active sprint, and only offers to go back', async () => {
      access.failure = new RoomFailure('no_active_sprint');

      const page = await open();

      expect(text(page, 'room-failure-message')).toContain('no tiene un sprint activo');
      expect(page.querySelector('[data-testid="room-retry"]')).toBeNull();
    });

    it('says the daily is not open, and only offers to go back', async () => {
      access.failure = new RoomFailure('daily_not_open');

      const page = await open();

      expect(text(page, 'room-failure-message')).toContain('no está abierta');
      expect(page.querySelector('[data-testid="room-retry"]')).toBeNull();
      expect(page.querySelector('[data-testid="room-back"]')).not.toBeNull();
    });

    it('says the room is not available, and offers to try again', async () => {
      access.failure = new RoomFailure('service_unavailable');

      const page = await open();

      expect(text(page, 'room-failure-message')).toBe(
        'La sala no está disponible en este momento.',
      );
      expect(page.querySelector('[data-testid="room-retry"]')).not.toBeNull();
    });

    it('says the access could not be validated when LiveKit refuses the token twice', async () => {
      room.connectFailures.push(
        new RoomFailure('token_rejected'),
        new RoomFailure('token_rejected'),
      );

      const page = await open();

      expect(text(page, 'room-failure-message')).toBe('No pudimos validar tu acceso a la sala.');
    });

    it('says something went wrong for anything else', async () => {
      access.failure = new RoomFailure('unexpected');

      const page = await open();

      expect(text(page, 'room-failure-message')).toBe('Algo salió mal al entrar a la sala.');
    });
  });

  // ------------------------------------------------ the layout of the room (AGI-61) --
  describe('the layout', () => {
    it('shows the status of Agilina, the turn, the participants and the actions', async () => {
      const page = await open();

      expect(text(page, 'room-agilina-status')).toBe('Estado de Agilina Aún no está en la sala');
      expect(text(page, 'room-turn')).toBe('Turno de Sin turno activo');
      expect(text(page, 'room-participants')).toBe('Participantes');
      expect(page.querySelector('#room-actions-title')?.textContent.trim()).toBe('Acciones');
      expect(text(page, 'room-status')).toBe('Conectado');
      expect(text(page, 'microphone-on')).toBe('Micrófono activo');
    });

    it('does not show the room while it is connecting', async () => {
      room.connect = () => new Promise<void>(() => undefined);

      const page = await open();

      expect(page.querySelector('[data-testid="room-participants"]')).toBeNull();
      expect(page.querySelector('[data-testid="room-agilina-status"]')).toBeNull();
    });

    it('does not show the room when it could not enter', async () => {
      access.failure = new RoomFailure('no_access');

      const page = await open();

      expect(page.querySelector('[data-testid="room-participants"]')).toBeNull();
      expect(page.querySelector('[data-testid="room-actions"]')).toBeNull();
      expect(page.querySelector('[data-testid="room-failure"]')).not.toBeNull();
    });

    it('shows no transcript', async () => {
      const page = await open();

      expect(page.querySelector('[data-testid*="transcript"]')).toBeNull();
      expect(page.textContent).not.toMatch(/transcrip|subt[ií]tulo/i);
    });
  });

  // ------------------------------- criterion 4: the actions and leaving (AGI-139) --
  describe('the actions', () => {
    it('shows the controls of the ceremony disabled, and says they are not available yet', async () => {
      const page = await open();
      const calls = [...room.calls];

      for (const [testId, label] of [
        ['room-start-daily', 'Iniciar reunión diaria'],
        ['room-end-turn', 'Terminar turno'],
        ['room-end-ceremony', 'Terminar ceremonia'],
      ] as const) {
        const button = page.querySelector<HTMLButtonElement>(`[data-testid="${testId}"]`)!;
        expect(button.textContent.trim()).toBe(label);
        expect(button.disabled).toBeTrue();
        expect(button.getAttribute('aria-describedby')).toBe('room-actions-unavailable');
        button.click();
      }
      await settle();

      expect(text(page, 'room-actions-unavailable')).toBe('Todavía no están disponibles.');
      expect(page.querySelector('#room-actions-unavailable')).not.toBeNull();
      expect(room.calls).toEqual(calls);
    });

    it('leaves the room and goes back to the dashboard', async () => {
      const page = await open();
      const before = room.disconnects;

      expect(text(page, 'room-leave')).toBe('Salir de la sala');
      expect(page.querySelector('[data-testid="room-leave"]')?.getAttribute('href')).toBe(
        '/acme/teams/atlas',
      );
      click(page, 'room-leave');
      await settle();

      expect(TestBed.inject(Router).url).toBe('/acme/teams/atlas');
      expect(room.disconnects).toBe(before + 1);
    });

    it('offers to leave while reconnecting, and only to go back when the room is lost', async () => {
      const page = await open();

      room.emit({ kind: 'reconnecting' });
      await settle();
      expect(page.querySelector('[data-testid="room-leave"]')).not.toBeNull();

      room.emit({ kind: 'lost' });
      await settle();
      expect(page.querySelector('[data-testid="room-leave"]')).toBeNull();
      expect(page.querySelector('[data-testid="room-back"]')).not.toBeNull();
    });
  });

  // ------------------------------------- criterion 1: the participants (AGI-137) --
  describe('the participants', () => {
    beforeEach(() => {
      invited.participants = [
        aDailyParticipant('user-eva', 'Eva Prueba'),
        aDailyParticipant('user-ana', 'Ana Gil'),
      ];
    });

    /** Name, «· tú», email and presence of each row of the list, in order. */
    function rows(page: HTMLElement): string[] {
      const fields = [
        'participant-name',
        'participant-self',
        'participant-email',
        'participant-presence',
      ];
      return [...page.querySelectorAll<HTMLElement>('[data-testid="room-participants"] li')].map(
        (row) =>
          fields
            .map((field) => text(row, field))
            .filter((value) => value !== undefined)
            .join(' '),
      );
    }

    it('lists the invited with their name and email, and who of them is in the room', async () => {
      const page = await open();

      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });
      await settle();

      expect(rows(page)).toEqual([
        'Eva Prueba · tú eva@example.test Conectado',
        'Ana Gil ana@example.test Desconectado',
      ]);
    });

    it('shows who arrives and who leaves without reloading, and never Agilina', async () => {
      const page = await open();
      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });
      await settle();

      room.emit({
        kind: 'presence',
        present: [
          aPresence('user-eva', { local: true }),
          aPresence('user-ana'),
          aPresence('agilina', { agent: true }),
        ],
      });
      await settle();
      expect(rows(page)).toEqual([
        'Eva Prueba · tú eva@example.test Conectado',
        'Ana Gil ana@example.test Conectado',
      ]);

      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });
      await settle();
      expect(rows(page)[1]).toBe('Ana Gil ana@example.test Desconectado');
    });

    it('shows someone in the room who was not invited as «Participante»', async () => {
      const page = await open();

      room.emit({
        kind: 'presence',
        present: [aPresence('user-eva', { local: true }), aPresence('guest-1')],
      });
      await settle();

      expect(rows(page)[2]).toBe('Participante Conectado');
    });

    it('lists only who is in the room when the invited cannot be read', async () => {
      invited.failure = new Error('403');
      const page = await open();

      room.emit({ kind: 'presence', present: [aPresence('user-eva', { local: true })] });
      await settle();

      expect(rows(page)).toEqual(['Participante · tú Conectado']);
      expect(text(page, 'room-status')).toBe('Conectado');
    });
  });

  // ----------------------- criteria 2 and 3: who is speaking and Agilina (AGI-138) --
  describe('who is speaking and Agilina', () => {
    const everyone = [
      aPresence('user-eva', { local: true }),
      aPresence('user-ana'),
      aPresence('agilina', { agent: true }),
    ];

    beforeEach(() => {
      invited.participants = [
        aDailyParticipant('user-eva', 'Eva Prueba'),
        aDailyParticipant('user-ana', 'Ana Gil'),
      ];
    });

    /** The names of the rows that show the voice indicator. */
    function speakingRows(page: HTMLElement): (string | undefined)[] {
      return [...page.querySelectorAll<HTMLElement>('[data-testid="room-participants"] li')]
        .filter((row) => row.querySelector('[data-testid="participant-speaking"]') !== null)
        .map((row) => text(row, 'participant-name'));
    }

    it('says Agilina is in the room when an agent is, and not in the list', async () => {
      const page = await open();

      room.emit({ kind: 'presence', present: everyone });
      await settle();

      expect(text(page, 'room-agilina-status')).toBe('Estado de Agilina En la sala');
      expect(page.querySelectorAll('[data-testid="room-participants"] li').length).toBe(2);

      room.emit({ kind: 'presence', present: everyone.slice(0, 2) });
      await settle();
      expect(text(page, 'room-agilina-status')).toBe('Estado de Agilina Aún no está en la sala');
    });

    it('marks the row of who speaks and takes the mark away when they stop', async () => {
      const page = await open();
      room.emit({ kind: 'presence', present: everyone });
      await settle();

      room.emit({ kind: 'speaking', identities: ['user-ana'] });
      await settle();
      expect(speakingRows(page)).toEqual(['Ana Gil']);
      expect(text(page, 'room-speaking-announcer')).toBe('Está hablando: Ana Gil');

      room.emit({ kind: 'speaking', identities: [] });
      await settle();
      expect(speakingRows(page)).toEqual([]);
      expect(text(page, 'room-speaking-announcer')).toBe('');
    });

    it('shows the voice indicator on Agilina when she speaks, and announces her', async () => {
      const page = await open();
      room.emit({ kind: 'presence', present: everyone });
      await settle();

      room.emit({ kind: 'speaking', identities: ['user-eva', 'agilina'] });
      await settle();

      expect(text(page, 'room-agilina-speaking')).toBe('Hablando');
      expect(text(page, 'room-agilina-status')).toBe('Estado de Agilina En la sala Hablando');
      expect(speakingRows(page)).toEqual(['Eva Prueba']);
      expect(text(page, 'room-speaking-announcer')).toBe('Está hablando: Eva Prueba, Agilina');
    });

    it('announces someone with no name as «Participante»', async () => {
      const page = await open();
      room.emit({ kind: 'presence', present: [...everyone, aPresence('guest-1')] });
      room.emit({ kind: 'speaking', identities: ['guest-1'] });
      await settle();

      expect(text(page, 'room-speaking-announcer')).toBe('Está hablando: Participante');
    });

    it('keeps the announcer in the room, polite and only for screen readers', async () => {
      const page = await open();

      const announcer = page.querySelector('[data-testid="room-speaking-announcer"]');
      expect(announcer?.getAttribute('aria-live')).toBe('polite');
      expect(announcer?.classList).toContain('sr-only');
      expect(text(page, 'room-speaking-announcer')).toBe('');
      expect(page.querySelector('[data-testid="room-agilina-speaking"]')).toBeNull();
    });

    it('does not mistake who speaks for whose turn it is', async () => {
      const page = await open();
      room.emit({ kind: 'presence', present: everyone });
      room.emit({ kind: 'speaking', identities: ['user-ana', 'agilina'] });
      await settle();

      expect(text(page, 'room-turn')).toBe('Turno de Sin turno activo');
    });

    it('stops marking anyone once the connection is lost', async () => {
      const page = await open();
      room.emit({ kind: 'presence', present: everyone });
      room.emit({ kind: 'speaking', identities: ['user-ana'] });
      await settle();

      room.emit({ kind: 'lost' });
      await settle();

      expect(page.querySelector('[data-testid="participant-speaking"]')).toBeNull();
      expect(page.querySelector('[data-testid="room-speaking-announcer"]')).toBeNull();
    });
  });

  describe('the audio of the others', () => {
    it('offers to turn it on when the browser blocked it', async () => {
      const page = await open();

      room.emit({ kind: 'audio_blocked', blocked: true });
      await settle();
      expect(text(page, 'audio-blocked')).toContain('Tu navegador pausó el audio de la sala.');

      click(page, 'audio-resume');
      await settle();

      expect(room.audioResumed).toBe(1);
      expect(page.querySelector('[data-testid="audio-blocked"]')).toBeNull();
    });
  });
});
