import { type Observable } from 'rxjs';

import { type MicrophoneState } from '../domain/microphone-state';
import { type RoomAccess } from '../domain/room-access';
import { type RoomPresence } from '../domain/room-presence';

/**
 * Something that happened to the connection while the participant was in the room: the network
 * dropped and it is being recovered, it came back, it could not be recovered (or the room closed
 * it), the browser blocked or allowed again the playback of the others' audio, or someone entered
 * or left: `present` is everyone in the room now, the participant included.
 */
export type RoomChange =
  | { readonly kind: 'reconnecting' }
  | { readonly kind: 'reconnected' }
  | { readonly kind: 'lost' }
  | { readonly kind: 'audio_blocked'; readonly blocked: boolean }
  | { readonly kind: 'presence'; readonly present: readonly RoomPresence[] };

/**
 * Port towards the audio room, in the words of the product: no type of the SDK crosses it. The
 * LiveKit adapter is bound in app.config.ts. One room at a time: connecting again leaves the
 * previous one first.
 */
export abstract class RoomPort {
  /** What happens to the connection once it is up. */
  abstract readonly changes: Observable<RoomChange>;

  /**
   * Enters the room with this access and listens to everyone in it, those already there and
   * those who arrive. It fails with a `RoomFailure` (`token_rejected`, `service_unavailable`).
   */
  abstract connect(access: RoomAccess): Promise<void>;

  /**
   * Asks the browser for the microphone before entering the room, so that the person answers the
   * browser's question first and enters with the microphone ready. It never fails: a problem is
   * a state.
   */
  abstract requestMicrophone(): Promise<MicrophoneState>;

  /**
   * Once in the room, publishes the microphone asked for before or, if there is none, asks for it
   * again and publishes it. It never fails: a problem is a state.
   */
  abstract enableMicrophone(): Promise<MicrophoneState>;

  /** Plays the others' audio again after the browser blocked it; call it on a user's gesture. */
  abstract resumeAudio(): Promise<void>;

  /** Leaves the room, if in one. */
  abstract disconnect(): Promise<void>;
}
