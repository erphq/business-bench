export default {
  fetch(request, env) {
    const url = new URL(request.url);
    const publicHost = url.hostname === "businessbench.org" || url.hostname === "www.businessbench.org";

    // Consolidate HTTP and www before static assets can serve duplicate pages.
    // Restrict the rule to production hosts so local previews stay accessible.
    if (publicHost && (url.protocol !== "https:" || url.hostname !== "businessbench.org")) {
      url.protocol = "https:";
      url.hostname = "businessbench.org";
      url.port = "";
      return Response.redirect(url.href, 308);
    }

    // Preserve asset headers, sitemap redirects, and real 404 responses.
    return env.ASSETS.fetch(request);
  },
};
