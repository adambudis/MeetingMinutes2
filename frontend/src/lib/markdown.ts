const FENCE_OPEN = /^\s*```(?:markdown|md)?[ \t]*\n/i;
const FENCE_CLOSE = /\n[ \t]*```\s*$/;
const HEADING = /^ {0,3}#{1,6}(\s|$)/;
const FENCE_LINE = /^ {0,3}(```|~~~)/;

const indentOf = (line: string) => line.length - line.trimStart().length;

/**
 * Small LLMs often indent everything under a heading by 4+ spaces. In Markdown that turns the
 * whole section into an indented code block, so un-indent such runs (up to the next line that
 * is not indented). Fenced code blocks are left alone.
 */
export function dedentAfterHeadings(md: string): string {
  const lines = md.split('\n').map((l) => l.replace(/^\t+/, (tabs) => '    '.repeat(tabs.length)));
  let inFence = false;
  for (let i = 0; i < lines.length; i++) {
    if (FENCE_LINE.test(lines[i])) {
      inFence = !inFence;
      continue;
    }
    if (inFence || !HEADING.test(lines[i])) continue;

    let end = i + 1;
    let minIndent = Infinity;
    while (end < lines.length && (lines[end].trim() === '' || indentOf(lines[end]) >= 4)) {
      if (lines[end].trim() !== '') minIndent = Math.min(minIndent, indentOf(lines[end]));
      end++;
    }
    if (minIndent === Infinity) continue;
    for (let j = i + 1; j < end; j++) lines[j] = lines[j].trim() === '' ? '' : lines[j].slice(minIndent);
    i = end - 1;
  }
  return lines.join('\n');
}

/** Clean up LLM output before rendering it as Markdown. */
export function normalizeLlmMarkdown(text: string): string {
  let md = text;
  const open = md.match(FENCE_OPEN);
  if (open) md = md.slice(open[0].length).replace(FENCE_CLOSE, '\n'); // answer wrapped in ```markdown
  return dedentAfterHeadings(md);
}
