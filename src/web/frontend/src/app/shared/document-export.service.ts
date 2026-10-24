import { Injectable } from '@angular/core';
import { renderMarkdownToHtml } from './markdown';

/** Small export adapter for Markdown documents. Other formats can be added here later. */
@Injectable({ providedIn: 'root' })
export class DocumentExportService {
  downloadMarkdown(markdown: string, title: string, fallbackName: string): void {
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${this.fileStem(title, fallbackName)}.md`;
    anchor.hidden = true;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  /** Open a print-ready view; the browser's print dialog can save it as PDF. */
  openPrintView(markdown: string, title: string): boolean {
    const printWindow = window.open('', '_blank');
    if (!printWindow) return false;

    const safeTitle = this.escapeHtml(title || 'Résumé de séance');
    const renderedContent = renderMarkdownToHtml(markdown);
    const titleHeading = /^\s*#\s+/.test(markdown) ? '' : `<h1>${safeTitle}</h1>`;
    let didPrint = false;
    const triggerPrint = () => {
      if (didPrint || printWindow.closed) return;
      didPrint = true;
      printWindow.print();
    };
    printWindow.addEventListener('load', triggerPrint, { once: true });
    printWindow.document.open();
    printWindow.document.write(`<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${safeTitle}</title>
<style>
  @page { margin: 18mm; }
  * { box-sizing: border-box; }
  body { margin: 0; color: #202124; background: #fff; font: 11pt/1.6 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; overflow-wrap: anywhere; }
  main { max-width: 900px; margin: 0 auto; }
  h1, h2, h3, h4, h5 { line-height: 1.3; break-after: avoid; }
  p, li, blockquote { orphans: 3; widows: 3; }
  ul, ol, blockquote, pre, table { break-inside: avoid; }
  pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: .8em; border: 1px solid #ccc; }
  code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .92em; }
  blockquote { border-left: 3px solid #777; margin-left: 0; padding-left: 1em; color: #444; }
  table { width: 100%; border-collapse: collapse; font-size: 9pt; }
  th, td { border: 1px solid #bbb; padding: .4em .55em; text-align: left; vertical-align: top; }
  th { background: #eee; }
  a { color: inherit; text-decoration: underline; }
  @media screen { body { padding: 28px; background: #f4f4f4; } main { background: #fff; padding: 32px; box-shadow: 0 1px 8px #0002; } }
  @media print { a { text-decoration: none; } }
</style>
</head>
<body><main>${titleHeading}${renderedContent}</main></body>
</html>`);
    printWindow.document.close();
    printWindow.focus();
    // document.write() on about:blank can complete before the load handler runs
    // in some browsers, so keep a fallback after the document has been laid out.
    window.setTimeout(triggerPrint, 400);
    return true;
  }

  private fileStem(title: string, fallbackName: string): string {
    const normalized = (title || fallbackName)
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9_-]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 80);
    return normalized || fallbackName || 'resume-seance';
  }

  private escapeHtml(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}
