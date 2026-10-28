import { aPresence } from '@testing/room';

import { agilinaTextOf } from './agilina-text';

describe('agilina text', () => {
  const person = aPresence('user-eva', { local: true });

  it('is what the agent could not say out loud', () => {
    expect(
      agilinaTextOf([person, aPresence('agilina', { agent: true, agentText: 'Hola, equipo.' })]),
    ).toBe('Hola, equipo.');
  });

  it('is nothing while her voice works or she is not in the room', () => {
    expect(agilinaTextOf([person, aPresence('agilina', { agent: true })])).toBeNull();
    expect(agilinaTextOf([person])).toBeNull();
  });

  it('never comes from someone who is not an agent', () => {
    expect(agilinaTextOf([aPresence('user-ana', { agentText: 'Soy Agilina' })])).toBeNull();
  });
});
