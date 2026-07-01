(function () {
  "use strict";

  const LANG_NAMES = { en: "English", fr: "French", es: "Spanish", zh: "Chinese" };

  const socket = io();

  const el = (id) => document.getElementById(id);
  const lobby = el("lobby");
  const game = el("game");
  const statusMessage = el("status-message");
  const roomCodeBadge = el("room-code-badge");
  const scoreboard = el("scoreboard");
  const roleBanner = el("role-banner");
  const wordCard = el("word-card");
  const secretWordEl = el("secret-word");
  const guessesRemainingEl = el("guesses-remaining");
  const guesserStatus = el("guesser-status");
  const guessesRemainingGuesserEl = el("guesses-remaining-guesser");
  const flagDifficultBtn = el("flag-difficult-btn");
  const roundTimerEl = el("round-timer");
  const chatLog = el("chat-log");
  const chatInput = el("chat-input");
  const sendBtn = el("send-btn");
  const openGamesPanel = el("open-games-panel");
  const openGamesList = el("open-games-list");

  let currentRole = null; // "prompter" | "guesser"
  let currentRoomCode = null;
  let roundCount = 0;
  let currentTargetLang = null;
  let currentGuesserNativeLang = null;
  let timerInterval = null;
  let timeRemaining = 0;
  let matchPollInterval = null;

  function showStatus(message) {
    statusMessage.textContent = message || "";
  }

  function collectProfile() {
    return {
      name: el("name").value.trim() || "Player",
      native_lang: el("native-lang").value,
      target_lang: el("target-lang").value,
      level: el("level").value,
    };
  }

  el("create-room-btn").addEventListener("click", () => {
    const profile = collectProfile();
    if (profile.native_lang === profile.target_lang) {
      showStatus("Your confident language and learning language must differ.");
      return;
    }
    showStatus("");
    stopMatchPolling();
    socket.emit("create_room", profile);
  });

  el("find-match-btn").addEventListener("click", () => {
    const profile = collectProfile();
    if (profile.native_lang === profile.target_lang) {
      showStatus("Your confident language and learning language must differ.");
      return;
    }
    showStatus("");
    openGamesPanel.classList.remove("hidden");
    requestOpenGames();
    stopMatchPolling();
    matchPollInterval = setInterval(requestOpenGames, 3000);
  });

  function requestOpenGames() {
    const profile = collectProfile();
    socket.emit("list_open_games", { native_lang: profile.native_lang, target_lang: profile.target_lang });
  }

  function stopMatchPolling() {
    if (matchPollInterval) {
      clearInterval(matchPollInterval);
      matchPollInterval = null;
    }
  }

  socket.on("open_games", (data) => {
    openGamesList.innerHTML = "";
    if (!data.games.length) {
      const empty = document.createElement("div");
      empty.className = "no-games-message";
      empty.textContent = "No open games yet — try again in a moment, or create your own below.";
      openGamesList.appendChild(empty);
      return;
    }
    data.games.forEach((gameEntry) => {
      const row = document.createElement("div");
      row.className = "game-row";
      const info = document.createElement("span");
      info.className = "game-row-info";
      info.textContent = `${gameEntry.host_name} — ${gameEntry.level}`;
      const joinBtn = document.createElement("button");
      joinBtn.className = "btn-primary";
      joinBtn.textContent = "Join";
      joinBtn.addEventListener("click", () => {
        const profile = collectProfile();
        stopMatchPolling();
        showStatus("");
        socket.emit("join_room", { ...profile, code: gameEntry.code });
      });
      row.appendChild(info);
      row.appendChild(joinBtn);
      openGamesList.appendChild(row);
    });
  });

  el("join-room-btn").addEventListener("click", () => {
    const profile = collectProfile();
    const code = el("join-code").value.trim().toUpperCase();
    if (!code) {
      showStatus("Enter a room code to join.");
      return;
    }
    if (profile.native_lang === profile.target_lang) {
      showStatus("Your confident language and learning language must differ.");
      return;
    }
    showStatus("");
    socket.emit("join_room", { ...profile, code });
  });

  socket.on("error", (data) => {
    showStatus(data.message || "Something went wrong.");
  });

  socket.on("joined", (data) => {
    currentRoomCode = data.code;
    roomCodeBadge.textContent = data.code;
    stopMatchPolling();
    if (data.players.length < 2) {
      lobby.classList.add("hidden");
      game.classList.remove("hidden");
      addSystemMessage(`Waiting for an opponent to join room ${data.code}...`);
    }
  });

  socket.on("round_started", (data) => {
    lobby.classList.add("hidden");
    game.classList.remove("hidden");
    currentRole = data.role;
    roundCount += 1;

    if (roundCount > 1) {
      addDivider();
    }

    renderScoreboard(data.scores);
    currentTargetLang = data.target_lang;
    currentGuesserNativeLang = data.guesser_native_lang || null;
    startRoundTimer(data.time_limit_seconds);

    if (data.role === "prompter") {
      roleBanner.textContent = `You are the PROMPTER. Give hints in ${LANG_NAMES[data.target_lang]} without saying the word.`;
      roleBanner.className = "role-prompter";
      wordCard.classList.remove("hidden");
      guesserStatus.classList.add("hidden");
      secretWordEl.textContent = data.secret_word;
      guessesRemainingEl.textContent = `${data.guesses_remaining} guesses remaining`;
      chatInput.placeholder = `Type a hint in ${LANG_NAMES[data.target_lang]}...`;
    } else {
      const nativeName = LANG_NAMES[data.guesser_native_lang];
      const targetName = LANG_NAMES[data.target_lang];
      roleBanner.textContent = `You are the GUESSER. Read the hints in ${targetName} and answer in your own language, ${nativeName} — not ${targetName}.`;
      roleBanner.className = "role-guesser";
      wordCard.classList.add("hidden");
      guesserStatus.classList.remove("hidden");
      guessesRemainingGuesserEl.textContent = `${data.guesses_remaining} guesses remaining`;
      chatInput.placeholder = `Type your guess in ${nativeName} (not ${targetName})...`;
    }

    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.value = "";
    chatInput.focus();
  });

  socket.on("hint", (data) => {
    addChatMessage(data.from_name, data.text, data.from_sid === socket.id);
  });

  socket.on("hint_rejected", (data) => {
    addRejectedMessage(data.message);
  });

  socket.on("difficulty_flagged", (data) => {
    addSystemMessage(`😅 ${data.from_name} says this clue is too hard — try simpler words!`);
  });

  flagDifficultBtn.addEventListener("click", () => {
    socket.emit("flag_difficult");
    flagDifficultBtn.disabled = true;
    setTimeout(() => {
      flagDifficultBtn.disabled = false;
    }, 5000);
  });

  socket.on("guess", (data) => {
    addChatMessage(data.from_name, data.text, data.from_sid === socket.id);
  });

  socket.on("guess_result", (data) => {
    if (!data.correct) {
      if (data.wrong_language && currentRole === "guesser") {
        const nativeName = LANG_NAMES[currentGuesserNativeLang];
        const targetName = LANG_NAMES[currentTargetLang];
        addSystemMessage(
          `That's the ${targetName} word! Translate it into ${nativeName} instead. ${data.remaining} guesses left.`
        );
      } else {
        addSystemMessage(`Not quite. ${data.remaining} guesses left.`);
      }
      if (currentRole === "guesser") {
        guessesRemainingGuesserEl.textContent = `${data.remaining} guesses remaining`;
      }
    }
  });

  socket.on("round_result", (data) => {
    const revealed = Object.entries(data.revealed_word)
      .map(([lang, text]) => `${LANG_NAMES[lang] || lang}: ${text}`)
      .join(" · ");
    if (data.correct) {
      addSystemMessage(`🎉 ${data.winner_name} guessed it! (+${data.score_awarded} pts) — ${revealed}`, "win");
    } else if (data.timed_out) {
      addSystemMessage(`⏰ Time's up! — ${revealed}`, "lose");
    } else {
      addSystemMessage(`😢 Out of guesses! — ${revealed}`, "lose");
    }
    renderScoreboard(data.scores);
  });

  socket.on("opponent_left", () => {
    addSystemMessage("Your opponent disconnected. Refresh to start a new game.");
    chatInput.disabled = true;
    sendBtn.disabled = true;
    stopRoundTimer();
  });

  function sendCurrentInput() {
    const text = chatInput.value.trim();
    if (!text || !currentRole) return;
    if (currentRole === "prompter") {
      socket.emit("send_hint", { text });
    } else {
      socket.emit("send_guess", { text });
    }
    chatInput.value = "";
    chatInput.focus();
  }

  sendBtn.addEventListener("click", sendCurrentInput);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendCurrentInput();
  });

  function renderScoreboard(scores) {
    scoreboard.innerHTML = "";
    Object.entries(scores || {}).forEach(([sid, info]) => {
      const chip = document.createElement("span");
      chip.className = "score-chip";
      const label = sid === socket.id ? "You" : info.name;
      chip.textContent = `${label}: ${info.score}`;
      scoreboard.appendChild(chip);
    });
  }

  function addChatMessage(fromName, text, mine) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${mine ? "mine" : "theirs"}`;
    const nameEl = document.createElement("div");
    nameEl.className = "msg-name";
    nameEl.textContent = mine ? "You" : fromName;
    const textEl = document.createElement("div");
    textEl.textContent = text;
    wrap.appendChild(nameEl);
    wrap.appendChild(textEl);
    chatLog.appendChild(wrap);
    scrollChatToBottom();
  }

  function addRejectedMessage(message) {
    const wrap = document.createElement("div");
    wrap.className = "msg rejected";
    wrap.textContent = `⚠️ ${message}`;
    chatLog.appendChild(wrap);
    scrollChatToBottom();
  }

  function addSystemMessage(text, kind) {
    const wrap = document.createElement("div");
    wrap.className = `msg system${kind ? " " + kind : ""}`;
    wrap.textContent = text;
    chatLog.appendChild(wrap);
    scrollChatToBottom();
  }

  function addDivider() {
    const wrap = document.createElement("div");
    wrap.className = "msg system";
    wrap.textContent = "— next word —";
    chatLog.appendChild(wrap);
    scrollChatToBottom();
  }

  function scrollChatToBottom() {
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function startRoundTimer(limitSeconds) {
    stopRoundTimer();
    timeRemaining = limitSeconds;
    renderRoundTimer();
    timerInterval = setInterval(() => {
      timeRemaining = Math.max(0, timeRemaining - 1);
      renderRoundTimer();
      if (timeRemaining <= 0) {
        stopRoundTimer();
      }
    }, 1000);
  }

  function stopRoundTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  function renderRoundTimer() {
    const minutes = Math.floor(timeRemaining / 60);
    const seconds = String(timeRemaining % 60).padStart(2, "0");
    roundTimerEl.textContent = `⏱ ${minutes}:${seconds}`;
    roundTimerEl.classList.toggle("low-time", timeRemaining <= 15);
  }
})();
