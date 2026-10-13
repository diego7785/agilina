#!/usr/bin/env bash
# Valida que los commits de un pull request sigan la convención acordada en el
# Sprint 0: Conventional Commits con ámbito y referencia a la historia.
#
#   uso: validate-commits.sh <sha-base> <sha-cabeza>
#   local: ./.github/scripts/validate-commits.sh origin/main HEAD
set -uo pipefail

BASE="${1:-origin/main}"
CABEZA="${2:-HEAD}"

TIPOS="feat|fix|refactor|test|docs|chore|perf|build|ci"
AMBITOS="api|agent|stt|web|infra|docs|shared"
PATRON_ASUNTO="^(${TIPOS})(\((${AMBITOS})\))?!?: .+"
PATRON_REFERENCIA="^Refs: (AGI-[0-9]{1,5}|Sprint-0)$"
LARGO_MAXIMO_ASUNTO=72

errores=0
commits=$(git rev-list --no-merges "${BASE}..${CABEZA}")

if [ -z "$commits" ]; then
  echo "No hay commits nuevos que validar."
  exit 0
fi

for commit in $commits; do
  asunto=$(git log -1 --format=%s "$commit")
  cuerpo=$(git log -1 --format=%b "$commit")
  corto=$(git log -1 --format=%h "$commit")

  if ! printf '%s' "$asunto" | grep -Eq "$PATRON_ASUNTO"; then
    echo "::error::$corto — el asunto no sigue la convención: '$asunto'"
    echo "          formato esperado: tipo(ambito): descripcion en imperativo"
    echo "          tipos: ${TIPOS//|/, }"
    echo "          ámbitos: ${AMBITOS//|/, }"
    errores=$((errores + 1))
  fi

  if [ "${#asunto}" -gt "$LARGO_MAXIMO_ASUNTO" ]; then
    echo "::warning::$corto — el asunto tiene ${#asunto} caracteres; el límite acordado es $LARGO_MAXIMO_ASUNTO."
  fi

  if ! printf '%s\n' "$cuerpo" | grep -Eq "$PATRON_REFERENCIA"; then
    echo "::error::$corto — falta la referencia al backlog en el pie del commit."
    echo "          agrega una línea 'Refs: AGI-nnn' (o 'Refs: Sprint-0' para gestión de configuración)."
    errores=$((errores + 1))
  fi
done

total=$(printf '%s\n' "$commits" | wc -l | tr -d ' ')

if [ "$errores" -gt 0 ]; then
  echo ""
  echo "$errores problema(s) en $total commit(s). Corrígelos con 'git rebase -i' y vuelve a empujar."
  exit 1
fi

echo "$total commit(s) validados: convención y referencia al backlog correctas."
