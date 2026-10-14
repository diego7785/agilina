import { type TeamDashboard } from '@features/teams/domain/team-dashboard';

/**
 * The dashboard of Atlas in the middle of its sprint (Sprint 12, day 3 of 10), with the next daily at
 * 14:00 UTC of Thursday 2026-10-08 and its room opening ten minutes before. A test changes
 * only what it is about.
 */
export function aDashboard(changes: Partial<TeamDashboard> = {}): TeamDashboard {
  return {
    team: { id: 'atlas', name: 'Atlas', mode: 'support', label: 'scrum_master' },
    sprint: {
      number: 12,
      startDate: '2026-10-06',
      endDate: '2026-10-15',
      day: { number: 3, total: 10, phase: 'in_progress' },
    },
    nextCeremony: {
      type: 'daily',
      startsAt: '2026-10-08T14:00:00Z',
      joinOpensAt: '2026-10-08T13:50:00Z',
    },
    canConfigure: true,
    ...changes,
  };
}
