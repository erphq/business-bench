/** Browse neighboring tasks in a category or track, including both ends of the list. */
export function taskNeighbors<T extends { id: string }>(tasks: T[], currentId: string, limit = 4): T[] {
  const index = tasks.findIndex((task) => task.id === currentId);
  if (index < 0 || tasks.length < 2) return [];
  const neighbors: T[] = [];
  for (let distance = 1; neighbors.length < Math.min(limit, tasks.length - 1); distance++) {
    for (const direction of [1, -1]) {
      const task = tasks[(index + direction * distance + tasks.length) % tasks.length];
      if (task.id !== currentId && !neighbors.some((item) => item.id === task.id)) neighbors.push(task);
      if (neighbors.length >= Math.min(limit, tasks.length - 1)) break;
    }
  }
  return neighbors;
}

/** A short, verbatim preview of a published task request, ending at a word boundary. */
export function taskExcerpt(text: string, maxLength = 180): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= maxLength) return clean;
  const clipped = clean.slice(0, maxLength - 1);
  const boundary = clipped.lastIndexOf(" ");
  return (boundary > 0 ? clipped.slice(0, boundary) : clipped) + "…";
}
