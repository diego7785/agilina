import { type Provider } from '@angular/core';

import { NOW } from '@core/time/now';

/** A clock a test moves by hand: `clock.now = new Date(…)`. */
export class TestClock {
  now: Date;

  constructor(now: string) {
    this.now = new Date(now);
  }

  provide(): Provider {
    return { provide: NOW, useValue: () => this.now };
  }
}
