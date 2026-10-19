import { InjectionToken } from '@angular/core';
import {
  type AudioCaptureOptions,
  createLocalAudioTrack,
  type LocalAudioTrack,
  Room,
  type RoomOptions,
} from 'livekit-client';

import { nextRetryDelay } from '../domain/reconnect-budget';

/**
 * The room of a ceremony carries only audio. The SDK reconnects by itself when the network
 * drops, within the budget of `reconnect-budget.ts`; leaving the page leaves the room
 * (`disconnectOnPageLeave`, on by default).
 */
/** How the participant's voice is captured: cleaned up for a meeting. */
export const AUDIO_CAPTURE: AudioCaptureOptions = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

export const ROOM_OPTIONS: Partial<RoomOptions> = {
  adaptiveStream: false,
  dynacast: false,
  audioCaptureDefaults: AUDIO_CAPTURE,
  reconnectPolicy: {
    nextRetryDelayInMs: ({ retryCount, elapsedMs }) => nextRetryDelay(retryCount, elapsedMs),
  },
};

/**
 * Creates the LiveKit room of each connection. A token, so that the adapter's test hands over
 * a room that emits events without any network.
 */
/**
 * Asks the browser for the microphone as a LiveKit track, before there is any room. A token, so
 * that the adapter's test answers for the browser.
 */
export const LIVEKIT_MICROPHONE = new InjectionToken<() => Promise<LocalAudioTrack>>(
  'LIVEKIT_MICROPHONE',
  { providedIn: 'root', factory: () => () => createLocalAudioTrack(AUDIO_CAPTURE) },
);

export const LIVEKIT_ROOM_FACTORY = new InjectionToken<() => Room>('LIVEKIT_ROOM_FACTORY', {
  providedIn: 'root',
  factory: () => () => new Room(ROOM_OPTIONS),
});
