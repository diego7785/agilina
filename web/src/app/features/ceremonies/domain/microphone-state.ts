/**
 * What happened to the participant's microphone. Only `on` publishes audio; in every other
 * state the participant stays in the room as a listener: they hear the others but nobody
 * hears them.
 *
 * - `pending`: being turned on (the browser may be asking for the permission).
 * - `denied`: the browser was not given the permission (`NotAllowedError`).
 * - `not_found`: there is no microphone (`NotFoundError`).
 * - `unavailable`: there is one but it cannot be used (another application holds it, for example).
 * - `insecure_context`: the page is not on HTTPS (nor on `localhost`), where browsers offer no
 *   microphone at all.
 */
export type MicrophoneState =
  'pending' | 'on' | 'denied' | 'not_found' | 'unavailable' | 'insecure_context';
