"""tenant schema: what a tenant's database holds (identity, teams and ceremonies)

The whole schema of the database of one tenant, in one initial migration (AD-29): ``app_user``,
``team``, ``team_member``, ``invitation``, ``sprint``, ``sprint_participant``, ``ceremony``,
``ceremony_result``, ``transcript_segment`` and ``ceremony_event``, as
the reference schema (``agilina_schema.sql``) defines them, with the changes the stories made:
``team.created_by`` and ``invitation.created_by`` accept NULL, meaning "created by the platform
operator" (AD-22), and a team's name has at most 80 characters, which backs the ``TeamName``
rule of the domain (HU-05; ``char_length`` counts characters like Python's ``len`` does, so
both sides agree on the limit).

``sprint`` was created minimal by HU-06 (the team, the dates and the status: enough to answer
"does the team have a sprint in progress?") and HU-07 completes it: the daily's time as a UTC
anchor instant plus the IANA time zone it was captured in (AD-31; no column holds a local time),
and ``sprint_participant``, the daily's participants with their ``turn_order`` from 1. Both
foreign keys of a participant share its ``team_id``, so the database keeps every participant
someone who has been a member of the sprint's team. ``team_member`` rows are never deleted (a
removed member keeps theirs as ``removed``), so the foreign key cannot tell an active member
from a removed one: the ``Sprint`` aggregate admits only active members, and removing a member
takes them out of the active sprint's participants. The statuses are the glossary's (``planned``,
``active``, ``closed``), and the partial unique index makes the database keep a team to one
active sprint at most.

``ceremony`` is minimal (AGI-64): the team, the sprint and the scheduled instant, enough for the
agent worker to ask for a ceremony's context. Its foreign key shares ``team_id`` with the sprint's,
so a ceremony always belongs to a sprint of its own team. Nothing creates ceremonies yet but the
tests (AGI-59 does). What the worker delivers when the ceremony closes (AGI-126) is
``ceremony_result``, one per ceremony (its primary key) with the SHA-256 of the delivery, which
tells a retry of the same delivery from another one, and its ``transcript_segment`` and
``ceremony_event`` rows in the order they came (``position``, from 0). They all share the
ceremony's ``team_id`` through their foreign keys. ``ceremony_status`` and
``ceremony_event_type`` hold the values of the shared contract's enums.

Development is local, so this migration is rewritten, not added to, while nobody else holds
data that depends on it: ``make clean`` and ``make up`` build every database from it. From the
first shared deployment on, a change is a new migration.

Written as SQL on purpose, like every migration of this project: enums, triggers and
partial indexes are not something autogenerate reproduces, and the foreign keys between
contexts live here and not in the ORM models (each context's models know only their own
tables).

Revision ID: 0001_tenant_schema
Previous revision: none
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_tenant_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE = [
    # Case-insensitive text for emails.
    "CREATE EXTENSION IF NOT EXISTS citext",
    # ------------------------------------------------------------------ enums --
    "CREATE TYPE team_mode AS ENUM ('support', 'autonomous')",
    "CREATE TYPE team_language AS ENUM ('en', 'es')",
    "CREATE TYPE team_role AS ENUM ('admin', 'member')",
    "CREATE TYPE membership_status AS ENUM ('active', 'removed')",
    "CREATE TYPE invitation_status AS ENUM ('pending', 'accepted', 'expired', 'revoked')",
    "CREATE TYPE sprint_status AS ENUM ('planned', 'active', 'closed')",
    "CREATE TYPE ceremony_status AS ENUM "
    "('scheduled', 'in_progress', 'completed', 'cancelled', 'degraded')",
    "CREATE TYPE ceremony_event_type AS ENUM "
    "('ceremony_started', 'turn_started', 'turn_ended', 'degraded', 'ceremony_closed')",
    # --------------------------------------------------- updated_at maintenance --
    """
    CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
    BEGIN
        NEW.updated_at := now();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    # --------------------------------------------------------------- app_user --
    """
    CREATE TABLE app_user (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        keycloak_subject  TEXT        NOT NULL UNIQUE,
        email             CITEXT      NOT NULL UNIQUE,
        full_name         TEXT        NOT NULL,
        is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "COMMENT ON TABLE app_user IS 'Agilina user. Passwords and sessions live in Keycloak (AD-12).'",
    "COMMENT ON COLUMN app_user.keycloak_subject IS "
    "'The \"sub\" claim of the OIDC token: the only link with the identity provider.'",
    "CREATE TRIGGER trg_app_user_updated BEFORE UPDATE ON app_user "
    "FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    # ------------------------------------------------------------------- team --
    """
    CREATE TABLE team (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name        TEXT          NOT NULL,
        mode        team_mode     NOT NULL DEFAULT 'support',
        language    team_language NOT NULL DEFAULT 'en',
        created_by  UUID          REFERENCES app_user(id) ON DELETE RESTRICT,
        silence_threshold_seconds     SMALLINT NOT NULL DEFAULT 10
            CHECK (silence_threshold_seconds  BETWEEN 3 AND 120),
        stuck_turn_threshold_seconds  SMALLINT NOT NULL DEFAULT 30
            CHECK (stuck_turn_threshold_seconds BETWEEN 5 AND 300),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT team_name_not_blank CHECK (length(btrim(name)) > 0),
        CONSTRAINT team_name_max_length CHECK (char_length(name) <= 80)
    )
    """,
    "COMMENT ON COLUMN team.mode IS "
    "'Only effect: whether Agilina asks for approval before acting (HU-11, HU-42, HU-43).'",
    "COMMENT ON COLUMN team.created_by IS "
    "'NULL when the platform operator created the team to give it its first admin (AD-22).'",
    "COMMENT ON TABLE team IS 'No time zone: members can live in different countries (AD-20).'",
    "CREATE TRIGGER trg_team_updated BEFORE UPDATE ON team "
    "FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    # ------------------------------------------------------------ team_member --
    # The visible label (Admin / Scrum Master / Member) is NOT stored: it is derived
    # from role + team.mode (HU-04).
    """
    CREATE TABLE team_member (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        team_id        UUID              NOT NULL REFERENCES team(id)     ON DELETE CASCADE,
        user_id        UUID              NOT NULL REFERENCES app_user(id) ON DELETE RESTRICT,
        role           team_role         NOT NULL DEFAULT 'member',
        status         membership_status NOT NULL DEFAULT 'active',
        slack_user_id  TEXT,
        joined_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        removed_at     TIMESTAMPTZ,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT team_member_unique UNIQUE (team_id, user_id),
        CONSTRAINT team_member_removed_coherent
            CHECK ((status = 'removed') = (removed_at IS NOT NULL))
    )
    """,
    "CREATE UNIQUE INDEX team_member_slack_unique "
    "ON team_member (team_id, slack_user_id) WHERE slack_user_id IS NOT NULL",
    "CREATE INDEX team_member_user_idx ON team_member (user_id) WHERE status = 'active'",
    "CREATE TRIGGER trg_team_member_updated BEFORE UPDATE ON team_member "
    "FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    # ------------------------------------------------------------- invitation --
    # HU-02: no public registration. Single-use link that expires after 7 days.
    """
    CREATE TABLE invitation (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        team_id           UUID              NOT NULL REFERENCES team(id) ON DELETE CASCADE,
        email             CITEXT            NOT NULL,
        full_name         TEXT              NOT NULL,
        role              team_role         NOT NULL DEFAULT 'member',
        token_hash        TEXT              NOT NULL UNIQUE,
        status            invitation_status NOT NULL DEFAULT 'pending',
        expires_at        TIMESTAMPTZ       NOT NULL,
        created_by        UUID              REFERENCES team_member(id) ON DELETE RESTRICT,
        accepted_at       TIMESTAMPTZ,
        accepted_user_id  UUID REFERENCES app_user(id) ON DELETE SET NULL,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "COMMENT ON COLUMN invitation.token_hash IS "
    "'Only the hash. The clear token travels once, by email, and is never stored.'",
    "COMMENT ON COLUMN invitation.created_by IS "
    "'NULL when the platform operator issued it, to create a team''s first admin (AD-22).'",
    "CREATE UNIQUE INDEX invitation_pending_unique "
    "ON invitation (team_id, email) WHERE status = 'pending'",
    # ----------------------------------------------------------------- sprint --
    """
    CREATE TABLE sprint (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        team_id          UUID          NOT NULL REFERENCES team(id) ON DELETE CASCADE,
        number           INTEGER       NOT NULL,
        start_date       DATE          NOT NULL,
        end_date         DATE          NOT NULL,
        status           sprint_status NOT NULL DEFAULT 'planned',
        daily_time_utc   TIMESTAMPTZ   NOT NULL,
        daily_time_zone  TEXT          NOT NULL,
        created_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
        updated_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
        CONSTRAINT sprint_number_positive CHECK (number > 0),
        CONSTRAINT sprint_number_unique UNIQUE (team_id, number),
        CONSTRAINT sprint_dates_ordered CHECK (end_date >= start_date),
        CONSTRAINT sprint_daily_time_zone_not_blank CHECK (length(btrim(daily_time_zone)) > 0),
        CONSTRAINT sprint_id_team_unique UNIQUE (id, team_id)
    )
    """,
    "COMMENT ON TABLE sprint IS "
    "'A team''s sprint: its calendar dates (every day counts), the daily''s time and status. "
    "HU-06 created it; HU-07 adds the daily''s time and participants (AD-31).'",
    "COMMENT ON COLUMN sprint.number IS "
    "'The sprint''s number in its team (\"Sprint 12\"): 1 for the first, then the highest of the "
    "team plus one. The API assigns it when the sprint is saved; nobody types or changes it "
    "(HU-12).'",
    "COMMENT ON COLUMN sprint.daily_time_utc IS "
    "'The daily''s wall-clock time as a UTC anchor instant: never a local time (AD-31).'",
    "COMMENT ON COLUMN sprint.daily_time_zone IS "
    "'IANA time zone of the browser of whoever saved the sprint: it fixes the daily''s "
    "wall-clock time and the sprint''s calendar (AD-31).'",
    "CREATE INDEX sprint_team_idx ON sprint (team_id)",
    "CREATE UNIQUE INDEX sprint_one_active_per_team ON sprint (team_id) WHERE status = 'active'",
    "CREATE TRIGGER trg_sprint_updated BEFORE UPDATE ON sprint "
    "FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    # ----------------------------------------------------- sprint_participant --
    # The daily's participants (HU-07). Both foreign keys share team_id: the participant has a
    # membership (active or removed) in the very team the sprint belongs to. Being an active
    # member is the aggregate's rule, not the database's. The order of the list is the turn order.
    """
    CREATE TABLE sprint_participant (
        sprint_id   UUID        NOT NULL,
        team_id     UUID        NOT NULL,
        user_id     UUID        NOT NULL,
        turn_order  INTEGER     NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT sprint_participant_pkey PRIMARY KEY (sprint_id, user_id),
        CONSTRAINT sprint_participant_sprint_fk FOREIGN KEY (sprint_id, team_id)
            REFERENCES sprint(id, team_id) ON DELETE CASCADE,
        CONSTRAINT sprint_participant_member_fk FOREIGN KEY (team_id, user_id)
            REFERENCES team_member(team_id, user_id) ON DELETE CASCADE,
        CONSTRAINT sprint_participant_turn_order_unique UNIQUE (sprint_id, turn_order),
        CONSTRAINT sprint_participant_turn_order_positive CHECK (turn_order >= 1)
    )
    """,
    "COMMENT ON TABLE sprint_participant IS "
    "'The daily''s participants of a sprint (HU-07). The foreign key only ensures each one "
    "has a membership in the sprint''s team; that it is active is kept by the application, "
    "which takes a removed member out of the active sprint.'",
    "COMMENT ON COLUMN sprint_participant.turn_order IS "
    "'Position in the daily''s round, from 1: the order of the list is the turn order.'",
    # --------------------------------------------------------------- ceremony --
    """
    CREATE TABLE ceremony (
        id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        team_id       UUID        NOT NULL,
        sprint_id     UUID        NOT NULL,
        scheduled_at  TIMESTAMPTZ NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ceremony_sprint_fk FOREIGN KEY (sprint_id, team_id)
            REFERENCES sprint(id, team_id) ON DELETE CASCADE,
        CONSTRAINT ceremony_id_team_unique UNIQUE (id, team_id)
    )
    """,
    "COMMENT ON TABLE ceremony IS "
    "'A ceremony the agent worker facilitates, minimal (AGI-64): its team, its sprint and when "
    "it is scheduled. The foreign key keeps it in a sprint of its own team.'",
    "COMMENT ON COLUMN ceremony.scheduled_at IS "
    "'The instant the ceremony is scheduled, in UTC: it gives the sprint''s day N of M "
    "(AD-31).'",
    # -------------------------------------------------------- ceremony_result --
    """
    CREATE TABLE ceremony_result (
        ceremony_id           UUID            NOT NULL,
        team_id               UUID            NOT NULL,
        status                ceremony_status NOT NULL,
        started_at            TIMESTAMPTZ     NOT NULL,
        closed_at             TIMESTAMPTZ     NOT NULL,
        present_participants  UUID[]          NOT NULL,
        absent_participants   UUID[]          NOT NULL,
        degraded              BOOLEAN         NOT NULL,
        degradation_detail    TEXT,
        payload_sha256        TEXT            NOT NULL,
        received_at           TIMESTAMPTZ     NOT NULL,
        CONSTRAINT ceremony_result_pkey PRIMARY KEY (ceremony_id),
        CONSTRAINT ceremony_result_ceremony_fk FOREIGN KEY (ceremony_id, team_id)
            REFERENCES ceremony(id, team_id) ON DELETE CASCADE,
        CONSTRAINT ceremony_result_id_team_unique UNIQUE (ceremony_id, team_id),
        CONSTRAINT ceremony_result_payload_sha256_hex CHECK (payload_sha256 ~ '^[0-9a-f]{64}$')
    )
    """,
    "COMMENT ON TABLE ceremony_result IS "
    "'What the agent worker delivered when the ceremony closed (AGI-126): one per ceremony. "
    "Its segments and events are in transcript_segment and ceremony_event.'",
    "COMMENT ON COLUMN ceremony_result.payload_sha256 IS "
    "'SHA-256 of the canonical JSON of the delivery: the same delivery again is accepted "
    "without storing anything, another one is refused.'",
    "COMMENT ON COLUMN ceremony_result.received_at IS 'When the API stored it, in UTC.'",
    # ----------------------------------------------------- transcript_segment --
    """
    CREATE TABLE transcript_segment (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ceremony_id  UUID    NOT NULL,
        team_id      UUID    NOT NULL,
        position     INTEGER NOT NULL,
        user_id      UUID    NOT NULL,
        text         TEXT    NOT NULL,
        start_ms     INTEGER NOT NULL,
        end_ms       INTEGER NOT NULL,
        CONSTRAINT transcript_segment_result_fk FOREIGN KEY (ceremony_id, team_id)
            REFERENCES ceremony_result(ceremony_id, team_id) ON DELETE CASCADE,
        CONSTRAINT transcript_segment_position_unique UNIQUE (ceremony_id, position),
        CONSTRAINT transcript_segment_position_not_negative CHECK (position >= 0),
        CONSTRAINT transcript_segment_times_ordered CHECK (end_ms >= start_ms)
    )
    """,
    "COMMENT ON TABLE transcript_segment IS "
    "'The attributed transcript of a ceremony, one final fragment per row, in the order the "
    "worker delivered it (position, from 0).'",
    "COMMENT ON COLUMN transcript_segment.user_id IS "
    "'Who said it: a participant of the ceremony''s sprint, checked by the application.'",
    # --------------------------------------------------------- ceremony_event --
    """
    CREATE TABLE ceremony_event (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        ceremony_id  UUID                NOT NULL,
        team_id      UUID                NOT NULL,
        position     INTEGER             NOT NULL,
        type         ceremony_event_type NOT NULL,
        at           TIMESTAMPTZ         NOT NULL,
        user_id      UUID,
        CONSTRAINT ceremony_event_result_fk FOREIGN KEY (ceremony_id, team_id)
            REFERENCES ceremony_result(ceremony_id, team_id) ON DELETE CASCADE,
        CONSTRAINT ceremony_event_position_unique UNIQUE (ceremony_id, position),
        CONSTRAINT ceremony_event_position_not_negative CHECK (position >= 0)
    )
    """,
    "COMMENT ON TABLE ceremony_event IS "
    "'What happened in a ceremony, in the order the worker saw it (position, from 0).'",
    "COMMENT ON COLUMN ceremony_event.user_id IS "
    "'The participant the event is about (a turn); NULL for the ceremony itself.'",
]

DOWNGRADE = [
    "DROP TABLE ceremony_event",
    "DROP TABLE transcript_segment",
    "DROP TABLE ceremony_result",
    "DROP TABLE ceremony",
    "DROP TABLE sprint_participant",
    "DROP TABLE sprint",
    "DROP TABLE invitation",
    "DROP TABLE team_member",
    "DROP TABLE team",
    "DROP TABLE app_user",
    "DROP FUNCTION set_updated_at()",
    "DROP TYPE ceremony_event_type",
    "DROP TYPE ceremony_status",
    "DROP TYPE sprint_status",
    "DROP TYPE invitation_status",
    "DROP TYPE membership_status",
    "DROP TYPE team_role",
    "DROP TYPE team_language",
    "DROP TYPE team_mode",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
