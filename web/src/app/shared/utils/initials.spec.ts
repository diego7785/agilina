import { initialsOf } from './initials';

describe('initialsOf', () => {
  it('takes the first letter of the first two words', () => {
    expect(initialsOf('Ana María Pérez')).toBe('AM');
  });

  it('ignores extra spaces and writes the letters in capitals', () => {
    expect(initialsOf('  ana   gil ')).toBe('AG');
  });

  it('is empty for an empty name', () => {
    expect(initialsOf('')).toBe('');
  });
});
