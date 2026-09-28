import { describe, expect, test } from "bun:test";
import { renderMarkdown } from "../src/lib/markdown";

describe("paper math", () => {
  test("renders explicit inline and block TeX at build time with accessible MathML", () => {
    const { html, toc } = renderMarkdown(String.raw`## Acceptance

The indicator is \(Y_{sir}=\prod_j g_{ij}(a_{sir})\).

\[
\widehat p_s = \frac{1}{NR}\sum_{i,r}Y_{sir}
\]

## Evidence`, { math: true });
    expect(html.match(/class="katex"/g)?.length).toBe(2);
    expect(html).toContain('class="katex-display"');
    expect(html).toContain('<math xmlns="http://www.w3.org/1998/Math/MathML"');
    expect(html).toContain('encoding="application/x-tex"');
    expect(toc.map(({ id }) => id)).toEqual(["acceptance", "evidence"]);
    expect(html).not.toContain('id="widehat');
  });

  test("math is opt-in and dollar amounts never become equations", () => {
    const source = String.raw`The cost is $22.06 and $219.13; \(x_i\) is an indicator.`;
    expect(renderMarkdown(source).html).not.toContain('class="katex"');
    const { html } = renderMarkdown(source, { math: true });
    expect(html).toContain("$22.06 and $219.13");
    expect(html.match(/class="katex"/g)?.length).toBe(1);
  });

  test("TeX delimiters stay literal in inline, fenced, and indented code", () => {
    const source = String.raw`Use \`\(x_i\)\` and \`\[x_i\]\`.

\`\`\`text
\[
x_i
\]
\(x_i\)
\`\`\`

    \(x_i\)
    \[x_i\]`.replaceAll("\\`", "`");
    const { html } = renderMarkdown(source, { math: true });
    expect(html).not.toContain('class="katex"');
    expect(html).toContain(String.raw`<code>\(x_i\)</code>`);
    expect(html).toContain(String.raw`\[x_i\]`);
  });

  test("inline math does not consume adjacent emphasis or mathematical subscripts", () => {
    const { html } = renderMarkdown(String.raw`*Accepted when \(x_i + y_j = 1\).*`, { math: true });
    expect(html).toStartWith("<p><em>Accepted when ");
    expect(html).toContain(".</em></p>");
    expect(html).toContain(String.raw`x_i + y_j = 1</annotation>`);
  });

  test("invalid TeX fails the build instead of publishing a broken equation", () => {
    expect(() => renderMarkdown(String.raw`\(\notARealCommand{x}\)`, { math: true })).toThrow();
  });
});
