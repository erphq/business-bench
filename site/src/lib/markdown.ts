import { Marked, type MarkedExtension } from "marked";
import katex from "katex";

/** Explicit TeX delimiters keep currency and ordinary Markdown unambiguous.
 * Tokenize before Markdown escapes, leaving code spans and fenced code untouched. */
function mathExtension(): MarkedExtension {
  const render = (text: string, displayMode: boolean) => katex.renderToString(text.trim(), {
    displayMode, output: "htmlAndMathml", throwOnError: true, strict: "error", trust: false,
  });
  return {
    hooks: {
      emStrongMask(src) {
        return src.replace(/\\\([\s\S]*?\\\)/g, (match) => "a".repeat(match.length));
      },
    },
    extensions: [
      {
        name: "displayMath", level: "block",
        start(src) { return src.match(/(?:^|\n) {0,3}\\\[/)?.index; },
        tokenizer(src) {
          const match = /^ {0,3}\\\[([\s\S]+?)\\\][ \t]*(?:\n|$)/.exec(src);
          if (match) return { type: "displayMath", raw: match[0], text: match[1] };
        },
        renderer(token) { return render(token.text, true) + "\n"; },
      },
      {
        name: "inlineMath", level: "inline",
        start(src) { const index = src.indexOf("\\("); return index < 0 ? undefined : index; },
        tokenizer(src) {
          const match = /^\\\(([^\n]+?)\\\)/.exec(src);
          if (match) return { type: "inlineMath", raw: match[0], text: match[1] };
        },
        renderer(token) { return render(token.text, false); },
      },
    ],
  };
}

export function slugify(s: string) {
  return s.toLowerCase().replace(/<[^>]+>/g, "").replace(/[^a-z0-9\s-]/g, "").trim().replace(/\s+/g, "-").slice(0, 80);
}

/** Render repo markdown with stable heading ids and a table of contents. */
export function renderMarkdown(md: string, opts: { stripFirstH1?: boolean; linkBase?: string; math?: boolean } = {}) {
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
  if (opts.math) marked.use(mathExtension());
  let src = md;
  if (opts.stripFirstH1) src = src.replace(/^#\s[^\n]*\n/, "");
  const html = marked.parse(src) as string;
  return { html, toc };
}
