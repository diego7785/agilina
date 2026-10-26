import { aPresence } from '@testing/room';

import { AGILINA_ARRIVAL_BUDGET_MS, agilinaStatusOf } from './agilina-status';

describe('agilina status', () => {
  const person = aPresence('user-eva', { local: true });

  it('gives Agilina thirty seconds to arrive', () => {
    expect(AGILINA_ARRIVAL_BUDGET_MS).toBe(30_000);
  });

  it('is arriving while no agent told its state and the budget lasts', () => {
    expect(agilinaStatusOf([person], false)).toBe('arriving');
    expect(agilinaStatusOf([person, aPresence('agilina', { agent: true })], false)).toBe(
      'arriving',
    );
  });

  it('is the state the agent published', () => {
    expect(
      agilinaStatusOf(
        [person, aPresence('agilina', { agent: true, agentState: 'standby' })],
        false,
      ),
    ).toBe('standby');
    expect(
      agilinaStatusOf(
        [person, aPresence('agilina', { agent: true, agentState: 'no_facilitation' })],
        false,
      ),
    ).toBe('no_facilitation');
  });

  it('is unavailable once the budget runs out without an agent with a state', () => {
    expect(agilinaStatusOf([person], true)).toBe('unavailable');
    expect(agilinaStatusOf([person, aPresence('agilina', { agent: true })], true)).toBe(
      'unavailable',
    );
  });

  it('follows an agent that arrives late', () => {
    expect(
      agilinaStatusOf([person, aPresence('agilina', { agent: true, agentState: 'standby' })], true),
    ).toBe('standby');
  });
});
