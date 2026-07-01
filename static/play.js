"use strict";

const SECTIONS = ["join-form", "waiting", "question", "intermission", "finished"];
const SHAPE_LABELS = ["▲", "◆", "●", "■"];
const ANSWER_COLORS = ["#E21B3C", "#1368CE", "#D89E00", "#26890C"];

let ws = null;
let playerId = null;
let answered = false;

function showSection(id) {
  SECTIONS.forEach((s) => {
    document.getElementById(s).classList.toggle("active", s === id);
  });
}

// ---------------------------------------------------------------------------
// Join
// ---------------------------------------------------------------------------

document.getElementById("form-join").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = document.getElementById("player-name").value.trim();
  if (!name) return;

  ws = new WebSocket(`ws://${location.host}/ws/player`);

  ws.addEventListener("open", () => {
    ws.send(JSON.stringify({ type: "join", name }));
    showSection("waiting");
  });

  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    handleMessage(msg);
  });

  ws.addEventListener("close", () => {
    showSection("join-form");
  });
});

// ---------------------------------------------------------------------------
// Message dispatch
// ---------------------------------------------------------------------------

function handleMessage(msg) {
  switch (msg.type) {
    case "joined":
      playerId = msg.player_id;
      break;

    case "question_start":
      answered = false;
      document.getElementById("answer-feedback").textContent = "";
      renderButtons(msg.button_count);
      showSection("question");
      break;

    case "answer_received":
      document.getElementById("answer-feedback").textContent =
        "Reponse enregistree !";
      break;

    case "intermission":
      showSection("intermission");
      break;

    case "finished":
      document.getElementById("final-score").textContent =
        `Score : ${msg.score} pts`;
      document.getElementById("final-rank").textContent =
        `Classement : ${msg.rank} / ${msg.total_players}`;
      showSection("finished");
      break;
  }
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------

function renderButtons(count) {
  const container = document.getElementById("buttons-container");
  container.innerHTML = "";

  for (let i = 0; i < count; i++) {
    const btn = document.createElement("button");
    btn.className = "answer-btn";
    btn.textContent = SHAPE_LABELS[i];
    btn.style.background = ANSWER_COLORS[i];
    btn.addEventListener("click", () => onAnswer(i));
    container.appendChild(btn);
  }
}

function onAnswer(index) {
  if (answered || ws === null) return;
  answered = true;

  document.querySelectorAll(".answer-btn").forEach((btn) => {
    btn.disabled = true;
  });

  ws.send(JSON.stringify({ type: "answer", index }));
}
