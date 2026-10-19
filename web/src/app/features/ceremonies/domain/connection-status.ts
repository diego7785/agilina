/**
 * Where the participant's connection to the room stands: entering (asking for the token and
 * connecting), in the room, getting back after the network dropped, or out of it with a reason.
 */
export type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'failed';
