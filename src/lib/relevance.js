export const skillProfile = [
  "distributed systems",
  "go",
  "kafka",
  "cloud infra",
  "backend",
  "aws",
  "developer tools",
  "open source"
];

export function scoreStartup(startup, detail) {
  const haystack = [
    startup.name,
    startup.one_liner,
    startup.source,
    ...(startup.tags || []),
    detail?.hiring_signal,
    detail?.github?.primary_language
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  const matches = skillProfile.filter((keyword) => haystack.includes(keyword.toLowerCase()));
  const score = matches.length;

  return {
    score,
    matches,
    label: score >= 3 ? "High" : score >= 1 ? "Medium" : "Low"
  };
}

export function buildMockDetail(startup) {
  const relevance = scoreStartup(startup);
  const isTechnical = relevance.score > 0;
  const primaryLanguage = startup.tags?.find((tag) => ["Go", "Python", "TypeScript"].includes(tag)) || (isTechnical ? "Go" : "TypeScript");

  return {
    name: startup.name,
    summary: `${startup.name} helps teams move faster in ${startup.tags?.[0] || "their market"} with a focused product and a clear wedge. The strongest fit signal is ${relevance.matches[0] || "the company category"}, based on the browse data available right now.`,
    news: [
      `${startup.name} is showing early momentum in ${startup.tags?.[0] || "its category"}.`,
      "Recent public signals are still being synthesized by the live detail layer."
    ],
    hiring_signal: isTechnical ? "hiring" : "unclear",
    founders: ["Founder data pending live lookup"],
    funding_summary: "No verified funding information found in the local demo dataset.",
    contact: startup.website,
    github: {
      repo_url: isTechnical ? `https://github.com/search?q=${encodeURIComponent(startup.name)}` : null,
      stars: isTechnical ? 1280 + startup.name.length * 17 : null,
      primary_language: primaryLanguage,
      good_first_issue_count: isTechnical ? Math.max(1, startup.name.length % 7) : null,
      last_commit_date: "2026-07-08"
    }
  };
}
