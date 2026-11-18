export interface SseMessage {
  event: string;
  data: string;
}

/**
 * Incremental Server-Sent Events parser. Feed it text chunks as they arrive (they may split
 * events anywhere); it returns every event completed so far. Comment lines (": keep-alive")
 * are ignored.
 */
export class SseParser {
  private buffer = '';

  feed(chunk: string): SseMessage[] {
    this.buffer += chunk;
    const messages: SseMessage[] = [];
    let boundary: number;
    while ((boundary = this.buffer.indexOf('\n\n')) >= 0) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const message = parseBlock(block);
      if (message) messages.push(message);
    }
    return messages;
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = 'message';
  const data: string[] = [];
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value;
    else if (field === 'data') data.push(value);
  }
  return data.length ? { event, data: data.join('\n') } : null;
}
