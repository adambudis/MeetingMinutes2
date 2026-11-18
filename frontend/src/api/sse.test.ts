import { describe, expect, it } from 'vitest';

import { messageFromBody } from './client';
import { SseParser } from './sse';

describe('SseParser', () => {
  it('reassembles events split across chunks and skips heartbeats', () => {
    const parser = new SseParser();
    expect(parser.feed('event: progress\ndata: {"message":"Na')).toEqual([]);
    expect(parser.feed('čítám"}\n\n: keep-alive\n\nevent: result\ndata: {"segments":[]}\n')).toEqual([
      { event: 'progress', data: '{"message":"Načítám"}' },
    ]);
    expect(parser.feed('\n')).toEqual([{ event: 'result', data: '{"segments":[]}' }]);
  });

  it('joins multi-line data and defaults the event name', () => {
    expect(new SseParser().feed('data: a\ndata: b\n\n')).toEqual([{ event: 'message', data: 'a\nb' }]);
  });
});

describe('messageFromBody', () => {
  it('reads FastAPI error details', () => {
    expect(messageFromBody('{"detail":"Soubor je prázdný."}', 400)).toBe('Soubor je prázdný.');
    expect(messageFromBody('{"detail":[{"msg":"Input should be canary"}]}', 422)).toBe('Input should be canary');
  });

  it('falls back to a status message for non-JSON bodies', () => {
    expect(messageFromBody('<html>413</html>', 413)).toBe('Soubor je příliš velký.');
    expect(messageFromBody('', 502)).toBe('Server je nedostupný (HTTP 502).');
  });
});
