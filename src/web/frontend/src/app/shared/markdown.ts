/** Render the application's supported Markdown subset with escaped raw text. */
export function renderMarkdownToHtml(markdown: string): string {
  if (!markdown) return '';
  const escapeHtml = (value: string) => value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const inline = (value: string) => {
    let output = escapeHtml(value);
    output = output.replace(/`([^`]+)`/g, '<code>$1</code>');
    output = output.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)(?:\s+[^)]*)?\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    output = output.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    output = output.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    output = output.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    return output;
  };
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const blocks: string[] = [];
  let paragraph: string[] = [];
  let listType: 'ul' | 'ol' | null = null;
  let listItems: string[] = [];
  let codeLines: string[] = [];
  let inCode = false;
  const flushParagraph = () => { if (paragraph.length) { blocks.push(`<p>${paragraph.map(inline).join('<br>')}</p>`); paragraph = []; } };
  const flushList = () => { if (listType && listItems.length) blocks.push(`<${listType}>${listItems.map(item => `<li>${inline(item)}</li>`).join('')}</${listType}>`); listType = null; listItems = []; };
  const splitTableRow = (value: string): string[] => {
    let row = value.trim();
    if (row.startsWith('|')) row = row.slice(1);
    if (row.endsWith('|')) row = row.slice(0, -1);
    return row.split(/(?<!\\)\|/).map(cell => cell.replace(/\\\|/g, '|').trim());
  };
  const isTableSeparator = (value: string): boolean =>
    /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(value);
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    // Render standard Markdown tables instead of exposing pipe-delimited source.
    if (!inCode && line.includes('|') && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      flushParagraph(); flushList();
      const headers = splitTableRow(line);
      const separators = splitTableRow(lines[index + 1]);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes('|')) {
        rows.push(splitTableRow(lines[index]));
        index++;
      }
      index--;
      const columnCount = Math.max(1, headers.length, ...rows.map(row => row.length));
      const normalizeRow = (cells: string[]) => Array.from({ length: columnCount }, (_, column) => cells[column] ?? '');
      const textAlignment = (column: number): string => {
        const marker = separators[column] ?? '---';
        return marker.startsWith(':') && marker.endsWith(':') ? 'center' : marker.endsWith(':') ? 'right' : 'left';
      };
      const headingCells = normalizeRow(headers).map((cell, column) => `<th scope="col" style="text-align:${textAlignment(column)}">${inline(cell)}</th>`).join('');
      const bodyRows = rows.map(row => `<tr>${normalizeRow(row).map((cell, column) => `<td style="text-align:${textAlignment(column)}">${inline(cell)}</td>`).join('')}</tr>`).join('');
      blocks.push(`<div class="artifact-table-wrap" role="region" aria-label="Tableau du contenu" tabindex="0"><table><thead><tr>${headingCells}</tr></thead><tbody>${bodyRows}</tbody></table></div>`);
      continue;
    }
    if (/^\s*```/.test(line)) {
      flushParagraph(); flushList();
      if (inCode) { blocks.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`); codeLines = []; inCode = false; }
      else inCode = true;
      continue;
    }
    if (inCode) { codeLines.push(line); continue; }
    if (!line.trim()) { flushParagraph(); flushList(); continue; }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) { flushParagraph(); flushList(); const level = heading[1].length; blocks.push(`<h${level + 1}>${inline(heading[2])}</h${level + 1}>`); continue; }
    const unordered = /^\s*[-*+]\s+(.+)$/.exec(line);
    const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (unordered || ordered) {
      flushParagraph(); const nextType = unordered ? 'ul' : 'ol';
      if (listType && listType !== nextType) flushList();
      listType = nextType; listItems.push((unordered || ordered)![1]); continue;
    }
    const quote = /^\s*>\s?(.*)$/.exec(line);
    if (quote) { flushParagraph(); flushList(); blocks.push(`<blockquote><p>${inline(quote[1])}</p></blockquote>`); continue; }
    flushList(); paragraph.push(line);
  }
  if (inCode) blocks.push(`<pre><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
  flushParagraph(); flushList();
  return blocks.join('');
}
