import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUpRight,
  BriefcaseBusiness,
  CheckCircle2,
  Code2,
  ExternalLink,
  Filter,
  Github,
  Loader2,
  Radar,
  Search,
  SlidersHorizontal,
  Sparkles,
  Star,
  UsersRound,
  X
} from "lucide-react";
import { mockStartups } from "./data/mockStartups";
import { buildMockDetail, scoreStartup, skillProfile } from "./lib/relevance";
import "./styles.css";

function normalizeStartups(value) {
  return Array.isArray(value) && value.length > 0 ? value : mockStartups;
}

function sourceTone(source) {
  return {
    YC: "source-yc",
    ProductHunt: "source-ph",
    BetaList: "source-beta"
  }[source] || "source-default";
}

function topRelevantStartup(items) {
  return [...items].sort((a, b) => scoreStartup(b).score - scoreStartup(a).score || a.name.localeCompare(b.name))[0];
}

function App() {
  const initialStartup = topRelevantStartup(mockStartups);
  const [startups, setStartups] = useState(mockStartups);
  const [selected, setSelected] = useState(initialStartup);
  const [detail, setDetail] = useState(buildMockDetail(initialStartup));
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("All");
  const [tag, setTag] = useState("All");
  const [sortRelevant, setSortRelevant] = useState(true);
  const [usingFallback, setUsingFallback] = useState(true);

  useEffect(() => {
    fetch("/data/startups.json")
      .then((response) => (response.ok ? response.json() : []))
      .then((data) => {
        const normalized = normalizeStartups(data);
        const firstStartup = topRelevantStartup(normalized);
        setStartups(normalized);
        setSelected(firstStartup);
        setDetail(buildMockDetail(firstStartup));
        setUsingFallback(normalized === mockStartups);
      })
      .catch(() => {
        const firstStartup = topRelevantStartup(mockStartups);
        setStartups(mockStartups);
        setSelected(firstStartup);
        setDetail(buildMockDetail(firstStartup));
        setUsingFallback(true);
      });
  }, []);

  const tags = useMemo(() => {
    return ["All", ...Array.from(new Set(startups.flatMap((item) => item.tags || []))).sort()];
  }, [startups]);

  const sources = useMemo(() => {
    return ["All", ...Array.from(new Set(startups.map((item) => item.source).filter(Boolean))).sort()];
  }, [startups]);

  const visibleStartups = useMemo(() => {
    const lowerQuery = query.trim().toLowerCase();
    const filtered = startups.filter((startup) => {
      const matchesQuery = !lowerQuery || [startup.name, startup.one_liner, ...(startup.tags || [])].join(" ").toLowerCase().includes(lowerQuery);
      const matchesSource = source === "All" || startup.source === source;
      const matchesTag = tag === "All" || startup.tags?.includes(tag);
      return matchesQuery && matchesSource && matchesTag;
    });

    return filtered.sort((a, b) => {
      if (!sortRelevant) return a.name.localeCompare(b.name);
      return scoreStartup(b).score - scoreStartup(a).score || a.name.localeCompare(b.name);
    });
  }, [startups, query, source, tag, sortRelevant]);

  function selectStartup(startup) {
    setSelected(startup);
    setLoadingDetail(true);
    window.setTimeout(() => {
      setDetail(buildMockDetail(startup));
      setLoadingDetail(false);
    }, 520);
  }

  return (
    <main className="shell">
      <section className="topbar">
        <div className="brand">
          <span className="brand-mark"><Radar size={24} /></span>
          <div>
            <h1>Startup Radar</h1>
            <p>Live startup discovery tuned to your backend and cloud skill profile.</p>
          </div>
        </div>
        <div className="profile-strip" aria-label="Skill profile">
          {skillProfile.map((skill) => <span key={skill}>{skill}</span>)}
        </div>
      </section>

      <section className="metrics" aria-label="Startup radar metrics">
        <Metric icon={<Sparkles size={18} />} label="Startups" value={startups.length} />
        <Metric icon={<CheckCircle2 size={18} />} label="High Fit" value={startups.filter((startup) => scoreStartup(startup).label === "High").length} />
        <Metric icon={<Github size={18} />} label="Open Source Leads" value={startups.filter((startup) => scoreStartup(startup).score > 0).length} />
        <Metric icon={<BriefcaseBusiness size={18} />} label="Data Mode" value={usingFallback ? "Demo" : "Live JSON"} />
      </section>

      <section className="workspace">
        <aside className="browse-panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow"><Filter size={14} /> Browse</span>
              <h2>Find your next startup</h2>
            </div>
            <button className={`icon-toggle ${sortRelevant ? "active" : ""}`} onClick={() => setSortRelevant((value) => !value)} title="Sort by relevance">
              <SlidersHorizontal size={18} />
            </button>
          </div>

          <div className="search-row">
            <Search size={17} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, market, tag" />
            {query ? <button className="clear-button" onClick={() => setQuery("")} title="Clear search"><X size={16} /></button> : null}
          </div>

          <div className="filters">
            <select value={source} onChange={(event) => setSource(event.target.value)} aria-label="Source filter">
              {sources.map((item) => <option key={item}>{item}</option>)}
            </select>
            <select value={tag} onChange={(event) => setTag(event.target.value)} aria-label="Tag filter">
              {tags.map((item) => <option key={item}>{item}</option>)}
            </select>
          </div>

          <div className="card-list">
            {visibleStartups.map((startup) => {
              const relevance = scoreStartup(startup);
              const active = selected?.name === startup.name;
              return (
                <button key={`${startup.name}-${startup.source}`} className={`startup-card ${active ? "selected" : ""}`} onClick={() => selectStartup(startup)}>
                  <span className={`source-badge ${sourceTone(startup.source)}`}>{startup.source}</span>
                  <span className={`fit-badge fit-${relevance.label.toLowerCase()}`}>{relevance.label}</span>
                  <strong>{startup.name}</strong>
                  <span className="one-liner">{startup.one_liner}</span>
                  <span className="tag-row">{startup.tags?.slice(0, 4).map((item) => <em key={item}>{item}</em>)}</span>
                </button>
              );
            })}
          </div>
        </aside>

        <DetailPanel startup={selected} detail={detail} loading={loadingDetail} />
      </section>
    </main>
  );
}

function Metric({ icon, label, value }) {
  return (
    <div className="metric">
      <span>{icon}</span>
      <div>
        <strong>{value}</strong>
        <small>{label}</small>
      </div>
    </div>
  );
}

function DetailPanel({ startup, detail, loading }) {
  const relevance = scoreStartup(startup, detail);

  return (
    <section className="detail-panel">
      {loading ? (
        <div className="loading-state">
          <Loader2 className="spin" size={34} />
          <p>Fetching live profile signals...</p>
        </div>
      ) : (
        <>
          <div className="detail-hero">
            <div>
              <span className={`source-badge ${sourceTone(startup.source)}`}>{startup.source}</span>
              <h2>{startup.name}</h2>
              <p>{startup.one_liner}</p>
            </div>
            <a className="visit-link" href={startup.website} target="_blank" rel="noreferrer">
              <ExternalLink size={17} /> Website
            </a>
          </div>

          <div className="fit-panel">
            <div>
              <span className={`fit-orb fit-${relevance.label.toLowerCase()}`}>{relevance.label}</span>
              <div>
                <strong>Relevance to your profile</strong>
                <p>{relevance.matches.length ? relevance.matches.join(", ") : "No direct keyword overlap yet"}</p>
              </div>
            </div>
            <span className="score">{relevance.score}/8</span>
          </div>

          <div className="detail-grid">
            <InfoBlock title="Synthesized Summary" icon={<Sparkles size={18} />}>
              <p>{detail.summary}</p>
            </InfoBlock>
            <InfoBlock title="Founders" icon={<UsersRound size={18} />}>
              <p>{detail.founders?.length ? detail.founders.join(", ") : "No founder data found yet."}</p>
            </InfoBlock>
            <InfoBlock title="Hiring" icon={<BriefcaseBusiness size={18} />}>
              <p className="status-text">{detail.hiring_signal}</p>
            </InfoBlock>
            <InfoBlock title="Funding" icon={<Star size={18} />}>
              <p>{detail.funding_summary}</p>
            </InfoBlock>
          </div>

          <section className="wide-block">
            <h3>Recent Signals</h3>
            <ul>
              {(detail.news?.length ? detail.news : ["No significant recent news found."]).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>

          <section className="contribute">
            <div>
              <span><Code2 size={19} /></span>
              <div>
                <h3>Contribute Here</h3>
                <p>{detail.github?.repo_url ? `${detail.github.good_first_issue_count} good first issues, ${detail.github.stars?.toLocaleString()} stars, ${detail.github.primary_language}` : "No public repository found yet."}</p>
              </div>
            </div>
            {detail.github?.repo_url ? (
              <a href={detail.github.repo_url} target="_blank" rel="noreferrer">
                Open GitHub <ArrowUpRight size={17} />
              </a>
            ) : null}
          </section>
        </>
      )}
    </section>
  );
}

function InfoBlock({ title, icon, children }) {
  return (
    <article className="info-block">
      <h3>{icon}{title}</h3>
      {children}
    </article>
  );
}

createRoot(document.getElementById("root")).render(<App />);
