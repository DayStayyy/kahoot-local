"use strict";

const ws = new WebSocket(`ws://${location.host}/ws/host`);

const SECTIONS = ["lobby", "question", "intermission", "finished"];
const SHAPE_LABELS = ["▲", "◆", "●", "■"];
const ANSWER_COLORS = ["#E21B3C", "#1368CE", "#D89E00", "#26890C"];

let timerInterval = null;
let timerDuration = 0;
let timerStart = 0;
let lastCorrectIndices = [];
let lastAnswers = [];

function showSection(id) {
  SECTIONS.forEach((s) => {
    document.getElementById(s).classList.toggle("active", s === id);
  });
}

// ---------------------------------------------------------------------------
// Lobby helpers
// ---------------------------------------------------------------------------

const playerMap = {};

function refreshLobbyCount() {
  const count = Object.keys(playerMap).length;
  document.getElementById("lobby-player-count").textContent =
    `${count} joueur(s) connecte(s)`;
}

function refreshLobbyList() {
  const ul = document.getElementById("lobby-player-list");
  ul.innerHTML = "";
  Object.values(playerMap).forEach((name) => {
    const li = document.createElement("li");
    li.textContent = name;
    ul.appendChild(li);
  });
}

// ---------------------------------------------------------------------------
// Timer
// ---------------------------------------------------------------------------

function startTimerUI(durationSeconds) {
  clearInterval(timerInterval);
  timerDuration = durationSeconds;
  timerStart = Date.now();
  const bar = document.getElementById("q-timer-bar");

  timerInterval = setInterval(() => {
    const elapsed = (Date.now() - timerStart) / 1000;
    const remaining = Math.max(0, timerDuration - elapsed);
    const pct = (remaining / timerDuration) * 100;
    bar.style.width = `${pct}%`;
    if (remaining <= 0) clearInterval(timerInterval);
  }, 100);
}

function stopTimerUI() {
  clearInterval(timerInterval);
  document.getElementById("q-timer-bar").style.width = "0%";
}

// ---------------------------------------------------------------------------
// Answer slots
// ---------------------------------------------------------------------------

function renderAnswers(answers) {
  for (let i = 0; i < 4; i++) {
    const slot = document.getElementById(`ans-${i}`);
    if (i < answers.length) {
      slot.textContent = `${SHAPE_LABELS[i]}  ${answers[i]}`;
      slot.style.background = ANSWER_COLORS[i];
      slot.style.opacity = "1";
      slot.classList.remove("correct", "wrong", "hidden-slot");
    } else {
      slot.textContent = "";
      slot.style.background = "transparent";
      slot.classList.add("hidden-slot");
    }
  }
}

function renderCorrectAnswers(answers, correctIndices) {
  const container = document.getElementById("correct-answers");
  container.innerHTML = "";
  correctIndices.forEach((i) => {
    const slot = document.createElement("div");
    slot.className = "answer-slot";
    slot.textContent = `${SHAPE_LABELS[i]}  ${answers[i]}`;
    slot.style.background = ANSWER_COLORS[i];
    container.appendChild(slot);
  });
}

function highlightCorrect(correctIndices) {
  for (let i = 0; i < 4; i++) {
    const slot = document.getElementById(`ans-${i}`);
    if (slot.classList.contains("hidden-slot")) continue;
    if (correctIndices.includes(i)) {
      slot.classList.add("correct");
    } else {
      slot.classList.add("wrong");
    }
  }
}

// ---------------------------------------------------------------------------
// Leaderboard
// ---------------------------------------------------------------------------

function renderLeaderboard(containerId, leaderboard) {
  const ol = document.getElementById(containerId);
  ol.innerHTML = "";
  leaderboard.forEach((entry, idx) => {
    const li = document.createElement("li");
    li.textContent = `${idx + 1}. ${entry.name} — ${entry.score} pts`;
    ol.appendChild(li);
  });
}

// ---------------------------------------------------------------------------
// WebSocket handlers
// ---------------------------------------------------------------------------

ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case "state_snapshot":
      handleStateSnapshot(msg);
      break;

    case "player_joined":
      playerMap[msg.player_id] = msg.name;
      refreshLobbyCount();
      refreshLobbyList();
      break;

    case "player_left":
      delete playerMap[msg.player_id];
      refreshLobbyCount();
      refreshLobbyList();
      break;

    case "question_start":
      handleQuestionStart(msg);
      break;

    case "answer_count":
      document.getElementById("q-answer-count").textContent =
        `${msg.count} / ${msg.total_players} reponse(s)`;
      break;

    case "intermission":
      handleIntermission(msg);
      break;

    case "finished":
      stopTimerUI();
      renderLeaderboard("final-ranking", msg.leaderboard);
      showSection("finished");
      break;

    case "error":
      alert(`Erreur : ${msg.message}`);
      break;
  }
});

function handleStateSnapshot(msg) {
  if (msg.state === "LOBBY") {
    showSection("lobby");
  }
  if (msg.players) {
    msg.players.forEach((p) => { playerMap[p.id] = p.name; });
    refreshLobbyCount();
    refreshLobbyList();
  }
}

function handleQuestionStart(msg) {
  document.getElementById("q-index").textContent =
    `Question ${msg.index + 1} / ${msg.total}`;
  document.getElementById("q-text").textContent = msg.question;
  document.getElementById("q-answer-count").textContent = "0 reponse(s)";
  const img = document.getElementById("q-image");
  if (msg.image) {
    img.src = `/static/${msg.image}`;
    img.style.display = "block";
  } else {
    img.src = "";
    img.style.display = "none";
  }
  lastAnswers = msg.answers;
  renderAnswers(msg.answers);
  startTimerUI(msg.time_limit);
  showSection("question");
}

function handleIntermission(msg) {
  stopTimerUI();
  lastCorrectIndices = msg.correct_indices;
  highlightCorrect(msg.correct_indices);
  renderCorrectAnswers(lastAnswers, msg.correct_indices);
  renderLeaderboard("ranking-list", msg.leaderboard);
  showSection("intermission");
}

// ---------------------------------------------------------------------------
// Lobby controls
// ---------------------------------------------------------------------------

document.querySelectorAll('input[name="quiz"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    document.getElementById("btn-start").disabled = false;
  });
});

document.getElementById("btn-start").addEventListener("click", () => {
  const selected = document.querySelector('input[name="quiz"]:checked');
  if (!selected) return;
  ws.send(JSON.stringify({ type: "start_quiz", filename: selected.value }));
});

document.getElementById("btn-next").addEventListener("click", () => {
  ws.send(JSON.stringify({ type: "next_question" }));
});
