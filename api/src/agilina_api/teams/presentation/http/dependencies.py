"""Dependency providers declared by the teams presentation layer.

The composition root overrides them with the real handlers, so this layer never imports
the infrastructure one.
"""

from agilina_api.teams.application.commands.change_member_role import ChangeMemberRoleHandler
from agilina_api.teams.application.commands.create_team_as_admin import CreateTeamAsAdminHandler
from agilina_api.teams.application.commands.reconfigure_sprint import ReconfigureSprintHandler
from agilina_api.teams.application.commands.remove_member import RemoveMemberHandler
from agilina_api.teams.application.commands.start_sprint import StartSprintHandler
from agilina_api.teams.application.queries.get_active_sprint import GetActiveSprintHandler
from agilina_api.teams.application.queries.get_team import GetTeamHandler
from agilina_api.teams.application.queries.get_team_dashboard import GetTeamDashboardHandler
from agilina_api.teams.application.queries.get_team_user import GetTeamUserHandler
from agilina_api.teams.application.queries.list_my_teams import ListMyTeamsHandler
from agilina_api.teams.application.queries.list_team_members import ListTeamMembersHandler


def get_create_team_as_admin_handler() -> CreateTeamAsAdminHandler:
    raise NotImplementedError("Wired by the composition root")


def get_list_my_teams_handler() -> ListMyTeamsHandler:
    raise NotImplementedError("Wired by the composition root")


def get_get_team_handler() -> GetTeamHandler:
    raise NotImplementedError("Wired by the composition root")


def get_list_team_members_handler() -> ListTeamMembersHandler:
    raise NotImplementedError("Wired by the composition root")


def get_change_member_role_handler() -> ChangeMemberRoleHandler:
    raise NotImplementedError("Wired by the composition root")


def get_remove_member_handler() -> RemoveMemberHandler:
    raise NotImplementedError("Wired by the composition root")


def get_start_sprint_handler() -> StartSprintHandler:
    raise NotImplementedError("Wired by the composition root")


def get_reconfigure_sprint_handler() -> ReconfigureSprintHandler:
    raise NotImplementedError("Wired by the composition root")


def get_get_active_sprint_handler() -> GetActiveSprintHandler:
    raise NotImplementedError("Wired by the composition root")


def get_get_team_user_handler() -> GetTeamUserHandler:
    raise NotImplementedError("Wired by the composition root")


def get_get_team_dashboard_handler() -> GetTeamDashboardHandler:
    raise NotImplementedError("Wired by the composition root")
