"""Command line of the harness: ``run``, ``compare``, ``list-cases`` and ``validate-cases``.

Exit codes: 0 run finished (failing cases are results, not errors); 1 invalid configuration,
invalid case or existing run/CSV/aggregate (nothing written); 2 provider unavailable
(nothing written); 3 the run finished but some case ended with ``status=error``; 4 an
optional defense (LLM Guard or Llama Prompt Guard 2) is not installed, not accessible or
cannot load (nothing written).
"""

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, NoReturn

from purple_team.aggregation import Aggregate, CaseModeAggregate, ModeAggregate
from purple_team.cases import load_cases
from purple_team.clock import Clock, SystemClock
from purple_team.composition import (
    build_runner,
    load_validated_setup,
    run_comparison,
    run_measurement,
)
from purple_team.config import DefenseMode, ProviderName, load_config, parse_defense_modes
from purple_team.errors import (
    CaseFormatError,
    ConfigError,
    DefenseUnavailableError,
    RunExistsError,
)
from purple_team.paths import display_path
from purple_team.providers.base import ProviderUnavailableError
from purple_team.records import CaseStatus, RunRecord, atlas_cell

EXIT_OK: Final = 0
EXIT_INVALID: Final = 1
EXIT_PROVIDER_UNAVAILABLE: Final = 2
EXIT_CASE_ERRORS: Final = 3
EXIT_DEFENSE_UNAVAILABLE: Final = 4
PROGRAM: Final = "python3 -m purple_team"
YES: Final = "sí"
NO: Final = "no"
NOT_APPLICABLE: Final = "n/a"
PROVIDER_CHOICES: Final = "{" + ",".join(member.value for member in ProviderName) + "}"
DEFENSE_CHOICES: Final = "{" + ",".join(member.value for member in DefenseMode) + "}[,...]"
REPEAT_MIN: Final = 1
REPEAT_MAX: Final = 99
DEFAULT_REPEAT: Final = "1"
REPETITION_SINGULAR: Final = "repetición"
REPETITION_PLURAL: Final = "repeticiones"


class CliUsageError(Exception):
    """Invalid command line (exit code 1 instead of argparse's 2, reserved for providers)."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CliUsageError(message)


def build_parser() -> argparse.ArgumentParser:
    """Parser with the four subcommands."""
    parser = _ArgumentParser(
        prog=PROGRAM,
        description="Banco de pruebas de equipo púrpura del cierre de ceremonia de Agilina.",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMANDO")
    run = commands.add_parser("run", help="Ejecuta los casos y escribe inputs/ y outputs/.")
    _add_common_options(run)
    run.add_argument(
        "--defense",
        metavar=DEFENSE_CHOICES,
        help=(
            "Modo de defensa o lista separada por comas: off, own, llm-guard, own-llm-guard, "
            "prompt-guard, own-prompt-guard (on = own)."
        ),
    )
    run.add_argument("--run-id", dest="run_id", help="Fija el identificador de la corrida.")
    run.add_argument(
        "--repeat",
        default=DEFAULT_REPEAT,
        metavar="N",
        help=f"Repite cada modo N veces ({REPEAT_MIN}-{REPEAT_MAX}) y escribe un agregado.",
    )
    compare = commands.add_parser("compare", help="Corre sin y con defensa y compara.")
    _add_common_options(compare)
    for name, help_text in (
        ("list-cases", "Lista los casos disponibles."),
        ("validate-cases", "Valida los casos y sus respuestas del mock."),
    ):
        utility = commands.add_parser(name, help=help_text)
        utility.add_argument("--config", help="Archivo TOML de configuración.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    clock: Clock | None = None,
) -> int:
    """Run the command line and return the exit code."""
    env = dict(os.environ) if environ is None else environ
    active_clock = SystemClock() if clock is None else clock
    try:
        args = build_parser().parse_args(argv)
        return _dispatch(args, env, active_clock)
    except (CliUsageError, ConfigError, CaseFormatError, RunExistsError) as exc:
        _print_error(str(exc))
        return EXIT_INVALID
    except ProviderUnavailableError as exc:
        _print_error(str(exc))
        return EXIT_PROVIDER_UNAVAILABLE
    except DefenseUnavailableError as exc:
        _print_error(str(exc))
        return EXIT_DEFENSE_UNAVAILABLE


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Archivo TOML de configuración.")
    parser.add_argument("--provider", metavar=PROVIDER_CHOICES, help="Proveedor del modelo.")
    parser.add_argument(
        "--case",
        dest="cases",
        action="append",
        default=[],
        metavar="ID",
        help="Caso a ejecutar (repetible; por defecto, todos).",
    )
    parser.add_argument("--label", help="Etiqueta que se añade al run id.")


def _overrides(args: argparse.Namespace, modes: Sequence[DefenseMode]) -> dict[str, str]:
    names = ("config", "provider")
    overrides = {name: value for name in names if (value := getattr(args, name, None))}
    if modes:
        overrides["defense"] = modes[0].value
    return overrides


def _parse_repeat(text: str) -> int:
    if not text.isdigit() or not REPEAT_MIN <= int(text) <= REPEAT_MAX:
        message = f"--repeat debe ser un entero entre {REPEAT_MIN} y {REPEAT_MAX}: {text!r}"
        raise ConfigError(message)
    return int(text)


def _dispatch(args: argparse.Namespace, environ: Mapping[str, str], clock: Clock) -> int:
    defense_text = getattr(args, "defense", None)
    requested = parse_defense_modes(defense_text) if defense_text else ()
    config = load_config(cli_overrides=_overrides(args, requested), environ=environ)
    if args.command == "list-cases":
        for case in load_cases(config.cases_dir):
            injection = case.injection
            kind = f"{injection.technique}/{injection.goal}" if injection else "control"
            print(f"{case.case_id}  [{kind}]  [{atlas_cell(case)}]  {case.title}")
        return EXIT_OK
    if args.command == "validate-cases":
        setup = load_validated_setup(config, ())
        shown = _shown(config.cases_dir)
        print(f"{len(setup.cases)} casos válidos en {shown} (contexto del equipo verificado)")
        return EXIT_OK
    if args.command == "compare":
        result = run_comparison(
            config,
            clock=clock,
            label=args.label,
            case_ids=args.cases,
            environ=environ,
        )
        _print_run(result.run_off, result.paths_off)
        _print_run(result.run_on, result.paths_on)
        print(f"Comparación: {_shown(result.csv_path)}")
        return _exit_code(result.run_off, result.run_on)
    modes = requested or (config.defense,)
    repeat = _parse_repeat(args.repeat)
    if len(modes) > 1 or repeat > 1:
        measurement = run_measurement(
            config,
            modes=modes,
            repeat=repeat,
            clock=clock,
            run_id=args.run_id,
            label=args.label,
            case_ids=args.cases,
            environ=environ,
        )
        for record, paths in zip(measurement.runs, measurement.paths, strict=True):
            _print_run(record, paths)
        _print_aggregate(measurement.aggregate, measurement.aggregate_paths)
        return _exit_code(*measurement.runs)
    runner = build_runner(
        config,
        clock=clock,
        run_id=args.run_id,
        label=args.label,
        case_ids=args.cases,
        environ=environ,
    )
    record = runner.run()
    _print_run(record, runner.record_paths)
    return _exit_code(record)


def _exit_code(*records: RunRecord) -> int:
    has_errors = any(case.status is CaseStatus.ERROR for run in records for case in run.cases)
    return EXIT_CASE_ERRORS if has_errors else EXIT_OK


def _print_run(record: RunRecord, paths: tuple[Path, Path]) -> None:
    print(f"Corrida {record.run_id} (proveedor={record.provider}, defensa={record.defense})")
    for case in record.cases:
        if case.status is CaseStatus.ERROR:
            print(f"  {case.case.case_id}  error: {case.error}")
            continue
        effect = case.evaluation.injection_effect if case.evaluation else None
        print(f"  {case.case.case_id}  efecto={_yes_no(effect)}  pasa={_yes_no(case.passed)}")
    totals = record.totals
    print(
        f"  Totales: {totals.cases} casos, {totals.passed} aprobados, {totals.failed} no "
        f"aprobados, {totals.errors} con error, {totals.injection_effect} con efecto de la "
        f"inyección, {totals.input_detections} detecciones, {totals.blocked_actions} bloqueos"
    )
    log_path, summary_path = paths
    print(f"  Registro: {_shown(log_path)}")
    print(f"  Resumen CSV: {_shown(summary_path)}")


def _print_aggregate(aggregate: Aggregate, paths: tuple[Path, Path]) -> None:
    noun = REPETITION_SINGULAR if aggregate.repeat == 1 else REPETITION_PLURAL
    print(f"Agregado {aggregate.group_id} ({aggregate.repeat} {noun} por modo)")
    for row in aggregate.rows:
        print(f"  {row.mode.value}  {row.case_id}  {_row_rates(row)}")
    for totals in aggregate.per_mode:
        print(f"  Totales {totals.mode.value}: {_mode_rates(totals)}")
    csv_path, json_path = paths
    print(f"  CSV: {_shown(csv_path)}")
    print(f"  JSON: {_shown(json_path)}")


def _row_rates(row: CaseModeAggregate) -> str:
    effect = _fraction(row.injection_effect, row.completed, row.injection_effect_rate)
    passed = _fraction(row.passed, row.completed, row.pass_rate)
    return f"efecto={effect}  pasa={passed}  errores={row.errors}"


def _mode_rates(totals: ModeAggregate) -> str:
    effect = _fraction(
        totals.injection_effect,
        totals.injected_case_runs,
        totals.injection_effect_rate,
    )
    passed = _fraction(totals.passed, totals.completed, totals.pass_rate)
    return f"efecto={effect}  pasa={passed}  errores={totals.errors}"


def _fraction(count: int | None, total: int, value: float | None) -> str:
    if count is None or value is None:
        return NOT_APPLICABLE
    return f"{count}/{total} ({value:.3f})"


def _yes_no(value: bool | None) -> str:
    if value is None:
        return NOT_APPLICABLE
    return YES if value else NO


def _shown(path: Path) -> str:
    return display_path(path, Path.cwd())


def _print_error(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
