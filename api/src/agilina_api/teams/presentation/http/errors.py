"""The teams errors and the HTTP response each one becomes.

``TeamsErrors`` is the catalog; ``TEAMS_ERRORS`` pairs each domain exception with an entry, and
the composition root registers it in ``shared.presentation.http.error_handlers``. A team that
does not exist answers ``SharedErrors.TEAM_NOT_FOUND``: identity answers it too; one without an
active sprint, ``SharedErrors.NO_ACTIVE_SPRINT``: ceremonies answers it too.
"""

from agilina_api.shared.presentation.http.api_error import ApiError, SharedErrors
from agilina_api.shared.presentation.http.error_handlers import ErrorMapping
from agilina_api.teams.domain.errors import (
    ActiveSprintExistsError,
    DailyParticipantNotAMemberError,
    DuplicateDailyParticipantError,
    InvalidTeamNameError,
    InvalidTimeZoneError,
    LastAdminError,
    MemberNotFoundError,
    NoActiveSprintError,
    NoDailyParticipantsError,
    RoleChangeDuringActiveSprintError,
    SprintEndsBeforeStartError,
    TeamNotFoundError,
)


class TeamsErrors:
    INVALID_TEAM_NAME = ApiError(
        422, "invalid_team_name", "The team name is blank or too long once trimmed."
    )
    MEMBER_NOT_FOUND = ApiError(
        404, "member_not_found", "The user is not an active member of the team."
    )
    LAST_ADMIN = ApiError(409, "last_admin", "The team cannot be left without an admin.")
    SPRINT_IN_PROGRESS = ApiError(
        409, "sprint_in_progress", "Roles do not change while a sprint is in progress."
    )
    SPRINT_ENDS_BEFORE_START = ApiError(
        422, "sprint_ends_before_start", "The sprint's end date is before its start date."
    )
    INVALID_TIME_ZONE = ApiError(
        422, "invalid_time_zone", "The time zone is not a known IANA time zone."
    )
    NO_DAILY_PARTICIPANTS = ApiError(
        422, "no_daily_participants", "The daily needs at least one participant."
    )
    DUPLICATE_DAILY_PARTICIPANT = ApiError(
        422, "duplicate_daily_participant", "A daily participant appears more than once."
    )
    DAILY_PARTICIPANT_NOT_A_MEMBER = ApiError(
        422,
        "daily_participant_not_a_member",
        "A daily participant is not an active member of the team.",
    )
    ACTIVE_SPRINT_EXISTS = ApiError(
        409, "active_sprint_exists", "The team already has an active sprint."
    )


TEAMS_ERRORS: tuple[ErrorMapping, ...] = (
    ErrorMapping(InvalidTeamNameError, TeamsErrors.INVALID_TEAM_NAME),
    ErrorMapping(TeamNotFoundError, SharedErrors.TEAM_NOT_FOUND),
    ErrorMapping(MemberNotFoundError, TeamsErrors.MEMBER_NOT_FOUND),
    ErrorMapping(LastAdminError, TeamsErrors.LAST_ADMIN),
    ErrorMapping(RoleChangeDuringActiveSprintError, TeamsErrors.SPRINT_IN_PROGRESS),
    ErrorMapping(NoActiveSprintError, SharedErrors.NO_ACTIVE_SPRINT),
    ErrorMapping(SprintEndsBeforeStartError, TeamsErrors.SPRINT_ENDS_BEFORE_START),
    ErrorMapping(InvalidTimeZoneError, TeamsErrors.INVALID_TIME_ZONE),
    ErrorMapping(NoDailyParticipantsError, TeamsErrors.NO_DAILY_PARTICIPANTS),
    ErrorMapping(DuplicateDailyParticipantError, TeamsErrors.DUPLICATE_DAILY_PARTICIPANT),
    ErrorMapping(DailyParticipantNotAMemberError, TeamsErrors.DAILY_PARTICIPANT_NOT_A_MEMBER),
    ErrorMapping(ActiveSprintExistsError, TeamsErrors.ACTIVE_SPRINT_EXISTS),
)
