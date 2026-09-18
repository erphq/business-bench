import { Marked } from "marked";

export function slugify(s: string) {
  return s.toLowerCase().replace(/<[^>]+>/g, "").replace(/[^a-z0-9\s-]/g, "").trim().replace(/\s+/g, "-").slice(0, 80);
}

/** Render repo markdown with stable heading ids and a table of contents. */
export function renderMarkdown(md: string, opts: { stripFirstH1?: boolean; linkBase?: string } = {}) {
  const toc: { depth: number; id: string; text: string }[] = [];
  const marked = new Marked({
    gfm: true,
    renderer: {
      heading({ tokens, depth }) {
        const text = this.parser.parseInline(tokens);
        const id = slugify(text);
        if (depth <= 3) toc.push({ depth, id, text: text.replace(/<[^>]+>/g, "") });
        return `<h${depth} id="${id}"><a class="anchor" href="#${id}">${text}</a></h${depth}>\n`;
      },
      link({ href, title, tokens }) {
        const text = this.parser.parseInline(tokens);
        let h = href;
        if (opts.linkBase && !/^(https?:|mailto:|#|\/)/.test(h)) h = opts.linkBase + h;
        const ext = /^https?:/.test(h) ? ' rel="noopener"' : "";
        return `<a href="${h}"${title ? ` title="${title}"` : ""}${ext}>${text}</a>`;
      },
    },
  });
  let src = md;
  if (opts.stripFirstH1) src = src.replace(/^#\s[^\n]*\n/, "");
  const html = marked.parse(src) as string;
  return { html, toc };
}
