import Box from '@mui/material/Box';
import { Component, useMemo, type ReactNode } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { normalizeLlmMarkdown } from '../lib/markdown';

/** Falls back to plain text if Markdown rendering throws (the WPF client did the same). */
class RenderFallback extends Component<{ text: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <Box sx={{ whiteSpace: 'pre-wrap' }}>{this.props.text}</Box> : this.props.children;
  }
}

/** LLM output as Markdown (GFM tables). Raw HTML is not rendered. */
export function MarkdownView({ text }: { text: string }) {
  const markdown = useMemo(() => normalizeLlmMarkdown(text), [text]);
  return (
    <RenderFallback text={text}>
      <Box
        sx={{
          fontSize: 13,
          lineHeight: 1.5,
          '& > :first-of-type': { mt: 0 },
          '& > :last-child': { mb: 0 },
          '& h1': { fontSize: 20, fontWeight: 500, mt: 1, mb: 1 },
          '& h2': { fontSize: 17, fontWeight: 500, mt: 2, mb: 0.75 },
          '& h3': { fontSize: 15, fontWeight: 500, mt: 1.5, mb: 0.5 },
          '& p': { my: 0.75 },
          '& ul, & ol': { pl: 2.5, my: 0.5 },
          '& li': { my: 0.25 },
          '& table': { display: 'block', overflowX: 'auto', borderCollapse: 'collapse', fontSize: 12, my: 1 },
          '& th, & td': { border: 1, borderColor: 'divider', px: 0.75, py: 0.5, textAlign: 'left', verticalAlign: 'top' },
          // keep headers on one line (the table scrolls horizontally instead of breaking "Vlastník")
          '& th': { bgcolor: 'action.selected', fontWeight: 500, whiteSpace: 'nowrap' },
          '& code': { fontFamily: 'Consolas, monospace', fontSize: 12, bgcolor: 'action.hover', px: 0.5, borderRadius: 0.5 },
          '& pre': { overflowX: 'auto', bgcolor: 'action.hover', p: 1, borderRadius: 1 },
          '& blockquote': { borderLeft: 3, borderColor: 'divider', m: 0, pl: 1.5, color: 'text.secondary' },
        }}
      >
        <Markdown remarkPlugins={[remarkGfm]}>{markdown}</Markdown>
      </Box>
    </RenderFallback>
  );
}
