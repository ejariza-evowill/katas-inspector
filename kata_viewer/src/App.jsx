import React, { useEffect, useMemo, useState } from "react";
import { fetchCsvObjects } from "./csv.js";

const TABS = {
  ranking: "ranking",
  rules: "rules",
};

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDateTime(value) {
  if (!value) {
    return "n/a";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(navigator.language, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

function getReportRange(katas) {
  const timestamps = katas
    .map((kata) => new Date(kata.completed_at).getTime())
    .filter((timestamp) => Number.isFinite(timestamp));

  if (timestamps.length === 0) {
    return "No completed kata timestamps found";
  }

  return `${formatDateTime(Math.min(...timestamps))} - ${formatDateTime(Math.max(...timestamps))}`;
}

function codewarsKataUrl(kata) {
  return `https://www.codewars.com/kata/${encodeURIComponent(kata.kata_slug || kata.kata_id)}`;
}

function medalForIndex(index) {
  return ["🥇", "🥈", "🥉"][index] ?? "";
}

function formatKyu(rankName) {
  const match = String(rankName || "").match(/^(\d+)\s+kyu$/i);
  return match ? match[1] : rankName || "n/a";
}

function App() {
  const [activeTab, setActiveTab] = useState(TABS.ranking);
  const [summaryRows, setSummaryRows] = useState([]);
  const [kataRows, setKataRows] = useState([]);
  const [scoringRules, setScoringRules] = useState([]);
  const [selectedUsername, setSelectedUsername] = useState("");
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [status, setStatus] = useState({ loading: true, error: "" });

  useEffect(() => {
    async function loadData() {
      try {
        const [summary, katas, rules] = await Promise.all([
          fetchCsvObjects("summary.csv"),
          fetchCsvObjects("completed_katas.csv"),
          fetchCsvObjects("kata_scoring_rules.csv"),
        ]);

        const sortedSummary = [...summary].sort((left, right) => {
          const scoreDelta = toNumber(right.total_score) - toNumber(left.total_score);
          if (scoreDelta !== 0) {
            return scoreDelta;
          }
          const solvedDelta = toNumber(right.solved_count) - toNumber(left.solved_count);
          if (solvedDelta !== 0) {
            return solvedDelta;
          }
          return left.name.localeCompare(right.name);
        });

        setSummaryRows(sortedSummary);
        setKataRows(katas);
        setScoringRules(rules);
        setStatus({ loading: false, error: "" });
      } catch (error) {
        setStatus({ loading: false, error: error.message });
      }
    }

    loadData();
  }, []);

  const selectedUser = useMemo(
    () => summaryRows.find((row) => row.username === selectedUsername) ?? summaryRows[0],
    [selectedUsername, summaryRows],
  );

  const selectedKatas = useMemo(
    () =>
      kataRows
        .filter((kata) => kata.username === selectedUser?.username)
        .sort((left, right) => new Date(right.completed_at) - new Date(left.completed_at)),
    [kataRows, selectedUser],
  );

  const selectedScore = useMemo(
    () => selectedKatas.reduce((sum, kata) => sum + toNumber(kata.awarded_score), 0),
    [selectedKatas],
  );

  const reportRange = useMemo(() => getReportRange(kataRows), [kataRows]);

  if (status.loading) {
    return <main className="app-shell loading">Loading CSV reports...</main>;
  }

  if (status.error) {
    return (
      <main className="app-shell">
        <section className="console-panel error-panel">
          <p className="panel-label">LOAD ERROR</p>
          <p>{status.error}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <nav className="tabs top-tabs" aria-label="Views">
        <button
          className={activeTab === TABS.ranking ? "active" : ""}
          type="button"
          onClick={() => setActiveTab(TABS.ranking)}
        >
          Ranking
        </button>
        <button
          className={activeTab === TABS.rules ? "active" : ""}
          type="button"
          onClick={() => setActiveTab(TABS.rules)}
        >
          Scoring Rules
        </button>
      </nav>

      <header className="app-header">
        <div className="ascii-rule" aria-hidden="true">
          <span></span>
        </div>
        <h1>.:: ꧁⎝ 𓆩༺&nbsp;&nbsp; KATAS RANKING&nbsp;&nbsp; ༻𓆪 ⎠꧂::.</h1>
        <div className="ascii-rule" aria-hidden="true">
          <span></span>
        </div>
        <p className="date-range">Date range: {reportRange}</p>
      </header>

      {activeTab === TABS.ranking ? (
        <RankingView
          summaryRows={summaryRows}
          selectedKatas={selectedKatas}
          selectedScore={selectedScore}
          selectedUser={selectedUser}
          selectedUsername={selectedUsername}
          isDetailOpen={isDetailOpen}
          onCloseDetail={() => {
            setIsDetailOpen(false);
            setSelectedUsername("");
          }}
          onSelectUser={(username) => {
            setSelectedUsername(username);
            setIsDetailOpen(true);
          }}
        />
      ) : (
        <ScoringRulesView scoringRules={scoringRules} />
      )}
    </main>
  );
}

function RankingView({
  summaryRows,
  selectedKatas,
  selectedScore,
  selectedUser,
  selectedUsername,
  isDetailOpen,
  onCloseDetail,
  onSelectUser,
}) {
  return (
    <section className={`ranking-layout ${isDetailOpen ? "detail-open" : ""}`}>
      <div className="console-panel">
        <div className="panel-title-row">
          <p className="panel-label">RANKING</p>
          <span>{summaryRows.length} users</span>
        </div>
        <div className="table-wrap">
          <table className="console-table ranking-table">
            <thead>
              <tr>
                <th>#</th>
                <th>name</th>
                <th>username</th>
                <th>katas</th>
                <th>score</th>
              </tr>
            </thead>
            <tbody>
              {summaryRows.map((row, index) => (
                <tr
                  className={row.username === selectedUsername ? "selected" : ""}
                  key={row.username}
                  onClick={() => onSelectUser(row.username)}
                >
                  <td>{index + 1}</td>
                  <td>
                    <span className="medal">{medalForIndex(index)}</span>
                    {row.name}
                  </td>
                  <td>{row.username}</td>
                  <td>{row.solved_count}</td>
                  <td>{row.total_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className={`console-panel detail-panel ${isDetailOpen ? "open" : ""}`} aria-hidden={!isDetailOpen}>
        <div className="panel-title-row">
          <div>
            <p className="panel-label">USER DETAIL</p>
            <h2>{selectedUser?.name ?? "No user selected"}</h2>
          </div>
          <div className="detail-actions">
            <div className="score-pill">
              <span>total</span>
              <strong>{selectedScore}</strong>
            </div>
            <button className="close-button" type="button" onClick={onCloseDetail} aria-label="Close user detail">
              x
            </button>
          </div>
        </div>

        <div className="table-wrap">
          <table className="console-table kata-table">
            <thead>
              <tr>
                <th>kata</th>
                <th>kyu</th>
                <th>score</th>
                <th>completed</th>
              </tr>
            </thead>
            <tbody>
              {selectedKatas.map((kata) => (
                <tr key={`${kata.username}-${kata.kata_id}-${kata.completed_at}`}>
                  <td>
                    <a href={codewarsKataUrl(kata)} rel="noreferrer" target="_blank">
                      {kata.kata_name}
                    </a>
                  </td>
                  <td>{formatKyu(kata.kata_rank_name)}</td>
                  <td>{kata.awarded_score || "0"}</td>
                  <td>{formatDateTime(kata.completed_at)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan="2">total score</td>
                <td>{selectedScore}</td>
                <td>{selectedKatas.length} katas</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </section>
  );
}

function ScoringRulesView({ scoringRules }) {
  return (
    <section className="console-panel rules-panel">
      <div className="panel-title-row">
        <p className="panel-label">SCORING RULES</p>
        <span>Official Codewars awarded score by rank</span>
      </div>
      <div className="table-wrap compact">
        <table className="console-table rules-table">
          <thead>
            <tr>
              <th>rank_name</th>
              <th>awarded_score</th>
            </tr>
          </thead>
          <tbody>
            {scoringRules.map((rule) => (
              <tr key={rule.rank_id}>
                <td>{rule.rank_name}</td>
                <td>{rule.awarded_score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default App;
