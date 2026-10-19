"""Turn application results into response models."""

from uuid import UUID

from agilina_api.teams.application.dtos import (
    ActiveSprintView,
    MemberView,
    TeamDashboardView,
    TeamMembersList,
    TeamView,
    UserTeamView,
)
from agilina_api.teams.presentation.http.schemas import (
    ActiveSprintResponse,
    CreatedTeamResponse,
    DailyParticipantResponse,
    DashboardSprintResponse,
    DashboardTeamResponse,
    MeResponse,
    MyTeamResponse,
    NextCeremonyResponse,
    RoleOptionResponse,
    SprintDayResponse,
    TeamDashboardResponse,
    TeamResponse,
    UserInTeamResponse,
    UsersInTeamResponse,
)
from agilina_shared import role_label
from agilina_shared.enums import CeremonyType, TeamRole
from agilina_shared.sprint_calendar import join_closes_at, join_opens_at


def present_created(team_id: UUID) -> CreatedTeamResponse:
    return CreatedTeamResponse(id=team_id)


def present_my_team(view: UserTeamView) -> MyTeamResponse:
    return MyTeamResponse(
        id=view.team_id,
        name=view.name,
        role=view.role,
        mode=view.mode,
        label=role_label(view.role, view.mode),
    )


def present_team(view: TeamView, role: TeamRole) -> TeamResponse:
    return TeamResponse(
        id=view.team_id,
        name=view.name,
        mode=view.mode,
        language=view.language,
        role=role,
        label=role_label(role, view.mode),
    )


def present_user(member: MemberView) -> UserInTeamResponse:
    return UserInTeamResponse(
        user_id=member.user_id,
        full_name=member.full_name,
        email=member.email,
        role=member.role,
        label=member.label,
        joined_at=member.joined_at,
        role_change_blocked_by=member.role_change_blocked_by,
        removal_blocked_by=member.removal_blocked_by,
    )


def present_users(members: TeamMembersList) -> UsersInTeamResponse:
    return UsersInTeamResponse(
        roles=[
            RoleOptionResponse(role=option.role, label=option.label) for option in members.roles
        ],
        users=[present_user(member) for member in members.members],
    )


def present_me(member: MemberView) -> MeResponse:
    return MeResponse(
        user_id=member.user_id,
        full_name=member.full_name,
        email=member.email,
        role=member.role,
        label=member.label,
        joined_at=member.joined_at,
    )


def present_active_sprint(view: ActiveSprintView) -> ActiveSprintResponse:
    sprint = view.sprint
    return ActiveSprintResponse(
        id=sprint.sprint_id,
        number=sprint.number,
        start_date=sprint.start_date,
        end_date=sprint.end_date,
        daily_time=sprint.daily_time,
        time_zone=sprint.time_zone,
        next_daily_at=view.next_daily_at,
        participants=[
            DailyParticipantResponse(user_id=user_id, turn_order=position)
            for position, user_id in enumerate(sprint.participants, start=1)
        ],
        day=SprintDayResponse(number=view.day.number, total=view.day.total, phase=view.day.phase),
    )


def present_team_dashboard(view: TeamDashboardView, role: TeamRole) -> TeamDashboardResponse:
    sprint = view.sprint
    daily_at = sprint.joinable_daily_at if sprint is not None else None
    return TeamDashboardResponse(
        team=DashboardTeamResponse(
            id=view.team.team_id,
            name=view.team.name,
            mode=view.team.mode,
            label=role_label(role, view.team.mode),
        ),
        sprint=(
            DashboardSprintResponse(
                number=sprint.sprint.number,
                start_date=sprint.sprint.start_date,
                end_date=sprint.sprint.end_date,
                day=SprintDayResponse(
                    number=sprint.day.number, total=sprint.day.total, phase=sprint.day.phase
                ),
            )
            if sprint is not None
            else None
        ),
        next_ceremony=(
            NextCeremonyResponse(
                type=CeremonyType.DAILY,
                starts_at=daily_at,
                join_opens_at=join_opens_at(daily_at),
                join_closes_at=join_closes_at(daily_at),
            )
            if daily_at is not None
            else None
        ),
        can_configure=role == TeamRole.ADMIN,
    )
