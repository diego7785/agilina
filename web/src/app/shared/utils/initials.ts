/** The first letters of the first two words of a name, in capitals: «Ana María Pérez» is «AM». */
export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter((word) => word.length > 0)
    .slice(0, 2)
    .map((word) => word.charAt(0).toUpperCase())
    .join('');
}
