/**
 * What the API hands over to enter the room of today's daily (AGI-59): the room, the LiveKit
 * token that lets this person in, until when it is valid and the server to connect to. It lives
 * only in memory for one connection: it is never stored, logged or reused.
 */
export interface RoomAccess {
  readonly roomName: string;
  readonly token: string;
  /** When the token stops being valid, in UTC (ISO 8601). */
  readonly expiresAt: string;
  /** The LiveKit server, `wss://…`: it comes with the token, so the client holds no setting. */
  readonly serverUrl: string;
}
