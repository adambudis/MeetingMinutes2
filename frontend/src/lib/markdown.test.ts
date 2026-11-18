import { describe, expect, it } from 'vitest';

import { dedentAfterHeadings, normalizeLlmMarkdown } from './markdown';

describe('normalizeLlmMarkdown', () => {
  it('un-indents sections a small model indented under headings', () => {
    // shape of real gemma3:4b output
    const md = [
      '### Téma 1: Rozpočet',
      '    **Shrnutí:**',
      '    Diskutovalo se o rozpočtu.',
      '',
      '    **Klíčové body:**',
      '    *   Marketing chce 20 %.',
      '        *   vnořený bod',
      '',
      '### Téma 2: Web',
      'Normální text.',
    ].join('\n');
    expect(dedentAfterHeadings(md)).toBe(
      [
        '### Téma 1: Rozpočet',
        '**Shrnutí:**',
        'Diskutovalo se o rozpočtu.',
        '',
        '**Klíčové body:**',
        '*   Marketing chce 20 %.',
        '    *   vnořený bod',
        '',
        '### Téma 2: Web',
        'Normální text.',
      ].join('\n'),
    );
  });

  it('leaves normal Markdown, nested lists and fenced code untouched', () => {
    const md = '# Souhrn\n\n- bod\n    - vnořený\n\n```\n# not a heading\n    code\n```\n';
    expect(normalizeLlmMarkdown(md)).toBe(md);
  });

  it('unwraps an answer wrapped in a markdown fence', () => {
    expect(normalizeLlmMarkdown('```markdown\n# Souhrn\n\n    text\n```')).toBe('# Souhrn\n\ntext\n');
    expect(normalizeLlmMarkdown('```python\nprint(1)\n```')).toBe('```python\nprint(1)\n```');
  });
});
