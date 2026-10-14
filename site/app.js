// Empty Ballot Lines dashboard. All data text goes through d3 .text(), never innerHTML.
const ATLAS = "https://cdn.jsdelivr.net/npm/us-atlas@3/states-albers-10m.json";
const NO_ELECTION = new Set(["Louisiana", "Mississippi", "New Jersey", "Virginia"]);
const pct = d3.format(".0%");
const num = d3.format(",");
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

const ui = { metric: "nocomp", sort: { key: "nocompPct", dir: -1 }, selected: null };
let DATA, byState, stateNames;

// Seat-weighted rollup. "unknown" seats (no candidates listed yet) are kept out of every rate.
function summarize(races) {
  const s = { seats: 0, known: 0, nocomp: 0, unopposed: 0, D: 0, R: 0, other: 0, both: 0, unknown: 0 };
  for (const r of races) {
    s.seats += r.seats;
    if (r.category === "unknown") { s.unknown += r.seats; continue; }
    s.known += r.seats;
    if (r.category === "two_party") { s.both += r.seats; continue; }
    s.nocomp += r.seats;
    if (r.category === "unopposed") s.unopposed += r.seats;
    s[r.majors === "D" || r.majors === "R" ? r.majors : "other"] += r.seats;
  }
  s.nocompPct = s.known ? s.nocomp / s.known : NaN;
  s.unopposedPct = s.known ? s.unopposed / s.known : NaN;
  return s;
}

const SEGMENTS = [
  ["both", "Both parties", "--both"],
  ["D", "Only Democrats", "--dem"],
  ["R", "Only Republicans", "--rep"],
  ["other", "Neither or shared", "--other"],
  ["unknown", "Not yet listed", "--unlisted"],
];

init().catch((e) => {
  d3.select("#meta").text(`Could not load data: ${e.message}`);
  console.error(e);
});

async function init() {
  const [data, atlas] = await Promise.all([d3.json("data/seats.json"), d3.json(ATLAS)]);
  DATA = data;
  stateNames = new Map(data.meta.chambers.map((c) => [c.state, c.state_name]));
  byState = d3.group(data.races, (r) => r.state);
  const updated = new Date(data.meta.generated_at);
  d3.select("#meta").text(`Updated ${updated.toLocaleDateString(undefined, { dateStyle: "medium" })} · ${num(data.races.length)} races in ${byState.size} states · Source: Wikipedia`);

  renderKpis();
  renderMap(atlas);
  renderTable();
  renderCoverage();

  d3.selectAll(".seg button").on("click", function () {
    ui.metric = this.dataset.metric;
    d3.selectAll(".seg button").attr("aria-checked", function () { return this.dataset.metric === ui.metric; });
    d3.select("#map-title").text(ui.metric === "nocomp" ? "Share of seats without major-party competition" : "Share of seats with no opponent at all");
    renderMap(atlas);
  });
  d3.select("#detail-close").on("click", () => select(null));
  d3.select("#only-gaps").on("change", renderRaces);
  d3.select("#race-search").on("input", renderRaces);
  const fromHash = location.hash.slice(1).toUpperCase();
  if (byState.has(fromHash)) select(fromHash, false);
}

function renderKpis() {
  const s = summarize(DATA.races);
  const items = [
    [num(s.seats), "seats up in November"],
    [pct(s.nocompPct), `without a D vs. R race (${num(s.nocomp)} seats)`],
    [num(s.D), "seats where only Democrats are running", "--dem"],
    [num(s.R), "seats where only Republicans are running", "--rep"],
    [pct(s.unopposedPct), `with no opponent at all (${num(s.unopposed)} seats)`],
  ];
  const k = d3.select("#kpis").selectAll(".kpi").data(items).join("div").attr("class", "kpi");
  k.selectAll("*").remove();
  k.append("div").attr("class", "v").text((d) => d[0]);
  const l = k.append("div").attr("class", "l");
  l.filter((d) => d[2]).append("span").attr("class", "sw").style("background", (d) => `var(${d[2]})`);
  l.append("span").text((d) => d[1]);
}

function stateStats() {
  return Array.from(byState, ([code, races]) => ({ code, name: stateNames.get(code), ...summarize(races) }));
}

function renderMap(atlas) {
  const stats = new Map(stateStats().map((s) => [s.name, s]));
  const key = ui.metric === "nocomp" ? "nocompPct" : "unopposedPct";
  const max = Math.max(0.1, Math.ceil(d3.max(stats.values(), (s) => s[key] || 0) * 10) / 10);
  const color = d3.scaleSequential(d3.interpolateRgb(css("--seq-lo"), css("--seq-hi"))).domain([0, max]);
  const features = topojson.feature(atlas, atlas.objects.states).features;
  const path = d3.geoPath();

  const svg = d3.select("#map").selectAll("svg").data([0]).join("svg")
    .attr("viewBox", "0 0 975 610").attr("role", "img")
    .attr("aria-label", "US map shaded by share of 2026 state legislative seats without competition");
  svg.selectAll("path.state").data(features, (f) => f.id).join("path")
    .attr("d", path)
    .attr("class", (f) => `state${NO_ELECTION.has(f.properties.name) ? " na" : ""}${stats.get(f.properties.name)?.code === ui.selected ? " sel" : ""}`)
    .attr("fill", (f) => {
      const s = stats.get(f.properties.name);
      return s && !isNaN(s[key]) ? color(s[key]) : css("--na");
    })
    .on("pointermove", (ev, f) => tip(ev, f.properties.name, stats.get(f.properties.name)))
    .on("pointerleave", () => d3.select("#tip").attr("hidden", true))
    .on("click", (ev, f) => { const s = stats.get(f.properties.name); if (s) select(s.code); });

  const lg = d3.select("#legend").html("");
  lg.append("span").text("0%");
  lg.append("span").attr("class", "ramp")
    .style("background", `linear-gradient(90deg, ${d3.range(0, 1.01, 0.25).map((t) => color(t * max)).join(",")})`);
  lg.append("span").text(pct(max));
  const na = lg.append("span").style("white-space", "nowrap");
  na.append("span").attr("class", "na-sw");
  na.append("span").text(" No election or no data");
}

function tip(ev, name, s) {
  const t = d3.select("#tip").attr("hidden", null).html("");
  t.append("b").text(name);
  if (!s) t.append("div").text(NO_ELECTION.has(name) ? "No legislative election in 2026" : "No data");
  else {
    t.append("div").text(`${pct(s.nocompPct)} without a D vs. R race (${num(s.nocomp)} of ${num(s.known)} seats)`);
    t.append("div").text(`${pct(s.unopposedPct)} with no opponent at all`);
    t.append("div").text(`Only D: ${num(s.D)} · Only R: ${num(s.R)}`);
    if (s.unknown) t.append("div").attr("class", "warn").text(`${num(s.unknown)} seats not yet listed`);
  }
  const node = t.node(), w = node.offsetWidth, h = node.offsetHeight;
  t.style("left", `${Math.min(ev.clientX + 12, innerWidth - w - 8)}px`)
   .style("top", `${ev.clientY + 12 + h > innerHeight ? ev.clientY - h - 12 : ev.clientY + 12}px`);
}

const COLUMNS = [
  ["name", "State"], ["seats", "Seats up"], ["nocompPct", "No D vs. R race"],
  ["D", "Only D"], ["R", "Only R"], ["unopposedPct", "No opponent"], ["unknown", "Not listed"],
];

function renderTable() {
  const { key, dir } = ui.sort;
  const rows = stateStats().sort((a, b) =>
    dir * (typeof a[key] === "string" ? a[key].localeCompare(b[key]) : (a[key] || 0) - (b[key] || 0)));
  const t = d3.select("#rank");
  t.selectAll("thead").data([0]).join("thead").selectAll("tr").data([0]).join("tr")
    .selectAll("th").data(COLUMNS).join("th")
    .attr("scope", "col")
    .attr("aria-sort", (c) => (c[0] === key ? (dir < 0 ? "descending" : "ascending") : null))
    .text((c) => c[1])
    .on("click", (ev, c) => {
      ui.sort = { key: c[0], dir: c[0] === key ? -dir : c[0] === "name" ? 1 : -1 };
      renderTable();
    });
  const tr = t.selectAll("tbody").data([0]).join("tbody").selectAll("tr").data(rows, (r) => r.code).join("tr")
    .on("click", (ev, r) => select(r.code)).order();
  tr.selectAll("td").data((r) => COLUMNS.map((c) => [c[0], r])).join("td").each(function ([k, r]) {
    const td = d3.select(this).html("");
    if (k === "nocompPct") {
      const cell = td.append("div").attr("class", "bar-cell");
      cell.append("span").text(pct(r[k]));
      cell.append("div").attr("class", "bar").append("i").style("width", `${(r[k] || 0) * 100}%`);
    } else if (k.endsWith("Pct")) td.text(pct(r[k]));
    else if (k === "unknown") td.text(r[k] ? num(r[k]) : "–").attr("class", r[k] ? "warn" : null);
    else td.text(typeof r[k] === "number" ? num(r[k]) : r[k]);
  });
}

function select(code, scroll = true) {
  ui.selected = code;
  ui.showAll = false;
  d3.selectAll("#map path.state").classed("sel", (f) => code && f.properties.name === stateNames.get(code));
  history.replaceState(null, "", code ? `#${code}` : location.pathname);
  const panel = d3.select("#detail").attr("hidden", code ? null : true);
  if (!code) return;
  const races = byState.get(code);
  const s = summarize(races);
  d3.select("#detail-title").text(`${stateNames.get(code)}: ${num(s.seats)} seats up`);
  const mk = d3.select("#detail-kpis").html("");
  [[pct(s.nocompPct), "without a D vs. R race"], [num(s.D), "only Democrats"], [num(s.R), "only Republicans"],
   [num(s.unopposed), "no opponent at all"]].forEach(([v, l]) => {
    const p = mk.append("span"); p.append("b").text(v); p.append("span").text(` ${l}`);
  });

  const ch = d3.select("#chambers").html("");
  for (const [chamber, rs] of d3.group(races, (r) => r.chamber)) {
    const cs = summarize(rs);
    const box = ch.append("div").attr("class", "chamber");
    const name = box.append("div").attr("class", "name");
    name.append("b").text(chamber);
    name.append("span").text(`${pct(cs.nocompPct)} without a D vs. R race · ${num(cs.seats)} seats`);
    box.append("div").attr("class", "stack").attr("role", "img")
      .attr("aria-label", SEGMENTS.map(([k, l]) => `${l}: ${cs[k]}`).join(", "))
      .selectAll("i").data(SEGMENTS.filter(([k]) => cs[k] > 0)).join("i")
      .style("flex", ([k]) => cs[k]).style("background", ([, , v]) => `var(${v})`)
      .attr("title", ([k, l]) => `${l}: ${num(cs[k])} seats`);
  }
  const lg = ch.append("div").attr("class", "stack-legend");
  SEGMENTS.forEach(([, l, v]) => lg.append("span").style("--c", `var(${v})`).text(l));
  const stale = DATA.meta.chambers.filter((c) => c.state === code && (c.stale || !c.races));
  if (stale.length) ch.append("p").attr("class", "warn")
    .text(`Data issue: ${stale.map((c) => `${c.chamber} ${c.races ? "is from an earlier refresh" : "could not be read"}`).join("; ")}.`);
  renderRaces();
  if (scroll) panel.node().scrollIntoView({ behavior: "smooth", block: "start" });
}

const TAG = (r) => r.category === "two_party" ? "Both parties"
  : r.category === "unknown" ? "Not yet listed"
  : `${r.category === "unopposed" ? "No opponent" : "No D vs. R"}${r.majors === "D" || r.majors === "R" ? ` · ${r.majors} wins` : ""}`;

function renderRaces() {
  if (!ui.selected) return;
  const onlyGaps = d3.select("#only-gaps").property("checked");
  const q = d3.select("#race-search").property("value").trim().toLowerCase();
  const races = byState.get(ui.selected).filter((r) =>
    (!onlyGaps || r.category === "one_party" || r.category === "unopposed") &&
    (!q || `${r.chamber} ${r.district} ${r.candidates.map((c) => c.name).join(" ")}`.toLowerCase().includes(q)));
  const ul = d3.select("#races").html("");
  d3.select("#detail .more").remove();
  if (!races.length) { ul.append("li").attr("class", "empty").text("No races match."); return; }
  const shown = ui.showAll ? races : races.slice(0, 24);  // keeps big states (NH, GA) scannable on a phone
  if (shown.length < races.length) d3.select("#detail").append("button").attr("class", "more")
    .text(`Show all ${races.length} races`).on("click", () => { ui.showAll = true; renderRaces(); });
  const li = ul.selectAll("li").data(shown).join("li");
  li.append("div").attr("class", "d").text((r) => `${r.district}${r.seats > 1 ? ` (${r.seats} seats)` : ""}`);
  li.append("div").attr("class", "k").text((r) => `${r.chamber} · ${TAG(r)}`);
  li.append("div").attr("class", "c").selectAll("div").data((r) => r.candidates).join("div")
    .call((d) => d.append("span").attr("class", (c) => `p ${c.party}`).text((c) => c.party === "O" ? "•" : c.party))
    .call((d) => d.append("span").text((c) => `${c.name} (${c.label})`));
  li.filter((r) => r.status).append("div").attr("class", "s").text((r) => r.status);
}

function renderCoverage() {
  const issues = DATA.meta.chambers.filter((c) => !c.races || c.stale || c.unknown_seats);
  const box = d3.select("#coverage");
  if (!issues.length) { box.append("p").text("All 88 chambers were read on the last refresh."); return; }
  box.append("p").text(`Coverage notes (${issues.length} of ${DATA.meta.chambers.length} chambers):`);
  box.append("ul").selectAll("li").data(issues).join("li").text((c) =>
    `${c.state_name} ${c.chamber}: ${!c.races ? "no district table found" : c.stale ? "kept from an earlier refresh" : `${c.unknown_seats} seat${c.unknown_seats > 1 ? "s" : ""} with no candidates listed yet`}`);
}
