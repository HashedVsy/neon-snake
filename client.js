// Neon Snake — standalone browser game. No Python server or WebSocket required.
(function () {
  'use strict';

  const canvas = document.getElementById('game-canvas');
  const ctx = canvas.getContext('2d');
  const W = 40, H = 30, HUD_ROWS = 2, CELL = 20;
  const bestKey = 'neon-snake-personal-best';
  let mode = 'SOLO';
  let state = 'START';
  let language = localStorage.getItem('neon-snake-language') || 'de';
  let best = Number(localStorage.getItem(bestKey)) || 0;
  let score = 0, apples = 0, speed = 11.5, wins = [0, 0];
  let player, opponent, food, lastStep = 0, soundOn = true;

  const $ = id => document.getElementById(id);
  const translations = {
    en: { solo:'Solo', versus:'2-Player', bot:'Vs Bot', score:'SCORE', best:'BEST', speed:'SPEED', length:'LENGTH',
      start:'Single-player high score challenge', move:'Move:', pause:'Pause / Resume:', play:'PLAY GAME', suspended:'SUSPENDED', paused:'GAME PAUSED',
      breathe:'Take a breather', resume:'RESUME', restart:'RESTART ROUND', over:'ROUND OVER', gameOver:'GAME OVER', final:'FINAL SCORE',
      personal:'PERSONAL BEST', apples:'APPLES EATEN', again:'PLAY AGAIN', language:'EN', player2:'Player 2:', reason:'Crashed into boundary wall' },
    de: { solo:'Solo', versus:'2 Spieler', bot:'Gegen Bot', score:'PUNKTE', best:'BESTE', speed:'TEMPO', length:'LÄNGE',
      start:'Einzelspieler-Highscore-Herausforderung', move:'Bewegen:', pause:'Pause / Fortsetzen:', play:'SPIEL STARTEN', suspended:'PAUSIERT', paused:'SPIEL PAUSIERT',
      breathe:'Kurze Verschnaufpause', resume:'FORTSETZEN', restart:'RUNDE NEU STARTEN', over:'RUNDE VORBEI', gameOver:'SPIEL VORBEI', final:'ENDPUNKTZAHL',
      personal:'PERSÖNLICHER BESTWERT', apples:'ÄPFEL GEGESSEN', again:'NOCHMAL SPIELEN', language:'DE', player2:'Spieler 2:', reason:'Kollision mit der Begrenzung' }
  };

  function applyLanguage() {
    const t = translations[language];
    const text = {
      'pill-solo':t.solo, 'pill-pvp':t.versus, 'pill-bot':t.bot, 'label-score':t.score, 'label-best':t.best,
      'label-speed':t.speed, 'label-length':t.length, 'start-mode-desc':t.start, 'start-p1-desc':t.move,
      'start-pause-desc':t.pause, 'start-action-text':t.play, 'pause-badge':t.suspended, 'pause-title':t.paused,
      'pause-subtitle':t.breathe, 'resume-action-text':t.resume, 'restart-action-text':t.restart, 'go-badge':t.over,
      'go-title':t.gameOver, 'go-final-label':t.final, 'go-best-label':t.personal, 'go-apples-label':t.apples,
      'playagain-action-text':t.again
    };
    Object.entries(text).forEach(([id, value]) => { if ($(id)) $(id).textContent = value; });
    const p2 = document.querySelector('#start-p2-row .ctrl-desc');
    if (p2) p2.textContent = t.player2;
    if ($('btn-language')) $('btn-language').textContent = t.language;
    document.documentElement.lang = language;
    localStorage.setItem('neon-snake-language', language);
    updateModeText();
  }

  function setOverlay(name) {
    $('overlay-start').style.display = name === 'START' ? 'flex' : 'none';
    $('overlay-pause').style.display = name === 'PAUSED' ? 'flex' : 'none';
    $('overlay-gameover').style.display = name === 'GAME_OVER' ? 'flex' : 'none';
  }

  function randomFood() {
    const occupied = new Set([...player, ...(opponent || [])].map(p => p.join(',')));
    let p;
    do { p = [2 + Math.floor(Math.random() * (W - 4)), HUD_ROWS + Math.floor(Math.random() * (H - HUD_ROWS))]; }
    while (occupied.has(p.join(',')));
    return p;
  }

  function resetRound() {
    const y = Math.floor((H + HUD_ROWS) / 2);
    player = [[8,y],[7,y],[6,y],[5,y]];
    opponent = mode === 'SOLO' ? null : [[W-9,y],[W-8,y],[W-7,y],[W-6,y]];
    player.dir = [1,0];
    if (opponent) opponent.dir = [-1,0];
    score = 0; apples = 0; speed = 11.5; food = randomFood(); lastStep = 0;
    $('go-reason').textContent = translations[language].reason;
    updateStats();
  }

  function startRound() { resetRound(); state = 'PLAYING'; setOverlay(null); }

  function setMode(next) {
    mode = next;
    wins = [0,0];
    resetRound();
    state = 'START';
    setOverlay('START');
    updateModeText();
  }

  function updateModeText() {
    ['SOLO','PVP','BOT'].forEach(m => { const el = $('pill-' + (m === 'SOLO' ? 'solo' : m === 'PVP' ? 'pvp' : 'bot')); if (el) el.classList.toggle('active', mode === m); });
    $('cluster-solo').style.display = mode === 'SOLO' ? 'flex' : 'none';
    $('cluster-versus').style.display = mode === 'SOLO' ? 'none' : 'flex';
    $('start-p2-row').style.display = mode === 'PVP' ? 'flex' : 'none';
  }

  function updateStats() {
    $('val-score').textContent = score;
    $('val-high').textContent = best;
    $('val-speed').textContent = speed.toFixed(1) + 'x';
    $('val-length').textContent = player ? player.length : 4;
    $('val-p1').textContent = score;
    $('val-p2').textContent = opponent ? opponent.score || 0 : 0;
    $('wins-p1').textContent = wins[0] + 'W';
    $('wins-p2').textContent = wins[1] + 'W';
    $('go-score').textContent = score;
    $('go-best').textContent = best;
    $('go-apples').textContent = apples;
  }

  function same(a,b) { return a[0] === b[0] && a[1] === b[1]; }
  function contains(snake, p) { return snake.some(x => same(x,p)); }
  function turn(snake, dir) { if (dir[0] !== -snake.dir[0] || dir[1] !== -snake.dir[1]) snake.dir = dir; }

  function chooseBotDirection() {
    const head = opponent[0];
    const options = [[1,0],[-1,0],[0,1],[0,-1]].filter(d => d[0] !== -opponent.dir[0] || d[1] !== -opponent.dir[1]);
    const safe = options.filter(d => {
      const next = [head[0] + d[0], head[1] + d[1]];
      return next[0] >= 0 && next[0] < W && next[1] >= HUD_ROWS && next[1] < H &&
        !contains(opponent.slice(1), next) && !contains(player, next);
    });
    if (!safe.length) return;
    safe.sort((a, b) => {
      const an = [head[0] + a[0], head[1] + a[1]];
      const bn = [head[0] + b[0], head[1] + b[1]];
      return Math.abs(an[0] - food[0]) + Math.abs(an[1] - food[1]) -
        Math.abs(bn[0] - food[0]) - Math.abs(bn[1] - food[1]);
    });
    turn(opponent, safe[0]);
  }

  function moveSnake(snake) {
    const head = snake[0];
    const next = [head[0] + snake.dir[0], head[1] + snake.dir[1]];
    snake.unshift(next);
    const ate = same(next, food);
    if (!ate) snake.pop();
    return { next, ate };
  }

  function endRound(reason, winner) {
    state = 'GAME_OVER';
    if (winner === 0 || winner === 1) wins[winner]++;
    $('go-reason').textContent = reason || translations[language].reason;
    updateStats(); setOverlay('GAME_OVER');
  }

  function updateGame() {
    if (state !== 'PLAYING') return;
    const result = moveSnake(player);
    const h = result.next;
    if (h[0] < 0 || h[0] >= W || h[1] < HUD_ROWS || h[1] >= H || contains(player.slice(1), h) || (opponent && contains(opponent, h))) {
      endRound(translations[language].reason, opponent ? 1 : 0); return;
    }
    if (result.ate) { score += 10; apples++; best = Math.max(best, score); localStorage.setItem(bestKey, best); food = randomFood(); speed = Math.min(22, 11.5 + apples * .35); }

    if (opponent) {
      if (mode === 'BOT') chooseBotDirection();
      const bot = moveSnake(opponent), oh = bot.next;
      if (oh[0] < 0 || oh[0] >= W || oh[1] < HUD_ROWS || oh[1] >= H || contains(opponent.slice(1), oh) || contains(player, oh)) {
        endRound(mode === 'BOT' ? 'Bot eliminated' : 'Player 2 eliminated', 0); return;
      }
      if (bot.ate) { opponent.score = (opponent.score || 0) + 10; food = randomFood(); }
    }
    updateStats();
  }

  function draw() {
    ctx.fillStyle = '#0d121c'; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.strokeStyle = '#161b22'; ctx.lineWidth = 1;
    for (let x=0;x<=W;x++) { ctx.beginPath(); ctx.moveTo(x*CELL,HUD_ROWS*CELL); ctx.lineTo(x*CELL,H*CELL); ctx.stroke(); }
    for (let y=HUD_ROWS;y<=H;y++) { ctx.beginPath(); ctx.moveTo(0,y*CELL); ctx.lineTo(W*CELL,y*CELL); ctx.stroke(); }
    ctx.fillStyle = '#081018'; ctx.fillRect(0,0,canvas.width,HUD_ROWS*CELL);
    ctx.strokeStyle = '#00b0ff'; ctx.strokeRect(0,HUD_ROWS*CELL,canvas.width,canvas.height-HUD_ROWS*CELL);
    if (food) { ctx.fillStyle='#ff3b30'; ctx.beginPath(); ctx.arc(food[0]*CELL+10,food[1]*CELL+10,7,0,Math.PI*2); ctx.fill(); }
    drawSnake(player,'#00e5ff'); if (opponent) drawSnake(opponent,'#ff3366');
    ctx.fillStyle='#f0f6fc'; ctx.font='bold 16px sans-serif'; ctx.fillText(`${translations[language].score}: ${score}`,12,16);
    ctx.fillStyle='#ffd700'; ctx.font='14px sans-serif'; ctx.fillText(`${translations[language].best}: ${best}`,canvas.width-115,16);
  }

  function drawSnake(snake, color) {
    if (!snake) return;
    snake.forEach((p,i) => { ctx.fillStyle = i === 0 ? '#ffffff' : color; ctx.fillRect(p[0]*CELL+2,p[1]*CELL+2,CELL-4,CELL-4); });
  }

  function frame(now) {
    if (!lastStep) lastStep = now;
    if (now - lastStep >= 1000 / speed) { lastStep = now; updateGame(); }
    draw(); requestAnimationFrame(frame);
  }

  function key(code) {
    if (code === 'Space' || code === 'Enter') { if (state === 'START' || state === 'GAME_OVER') startRound(); else if (state === 'PAUSED') { state='PLAYING'; setOverlay(null); } return; }
    if (code === 'KeyP' || code === 'Escape') { if (state === 'PLAYING') { state='PAUSED'; setOverlay('PAUSED'); } else if (state === 'PAUSED') { state='PLAYING'; setOverlay(null); } return; }
    if (code === 'KeyR') { startRound(); return; }
    if (code === 'Digit1') { setMode('SOLO'); return; } if (code === 'Digit2') { setMode('PVP'); return; } if (code === 'Digit3') { setMode('BOT'); return; }
    if (state !== 'PLAYING') return;
    const dirs = { ArrowUp:[0,-1],KeyW:[0,-1],ArrowDown:[0,1],KeyS:[0,1],ArrowLeft:[-1,0],KeyA:[-1,0],ArrowRight:[1,0],KeyD:[1,0] };
    if (dirs[code]) { if (mode === 'PVP' && ['KeyW','KeyA','KeyS','KeyD'].includes(code)) turn(opponent,dirs[code]); else turn(player,dirs[code]); }
  }

  document.addEventListener('keydown', e => { if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','KeyW','KeyA','KeyS','KeyD','Space','Enter','KeyP','KeyR','Escape','Digit1','Digit2','Digit3'].includes(e.code)) { e.preventDefault(); key(e.code); } });
  $('btn-start-action').addEventListener('click', () => key('Space'));
  $('btn-resume-action').addEventListener('click', () => key('Space'));
  $('btn-restart-action').addEventListener('click', () => key('KeyR'));
  $('btn-playagain-action').addEventListener('click', () => key('Space'));
  $('btn-language').addEventListener('click', () => { language = language === 'en' ? 'de' : 'en'; applyLanguage(); });
  $('btn-pause-toggle').addEventListener('click', () => key('KeyP'));
  $('btn-sound').addEventListener('click', () => { soundOn = !soundOn; $('svg-sound-on').style.display = soundOn ? '' : 'none'; $('svg-sound-off').style.display = soundOn ? 'none' : ''; });
  [['solo','SOLO'],['pvp','PVP'],['bot','BOT']].forEach(([id,m]) => $('pill-'+id).addEventListener('click', () => setMode(m)));
  document.querySelectorAll('.touch-btn[data-dir]').forEach(btn => btn.addEventListener('click', () => key(btn.dataset.dir === 'UP' ? 'ArrowUp' : btn.dataset.dir === 'DOWN' ? 'ArrowDown' : btn.dataset.dir === 'LEFT' ? 'ArrowLeft' : 'ArrowRight')));
  $('touch-action').addEventListener('click', () => key(state === 'PLAYING' ? 'KeyP' : 'Space'));

  resetRound(); applyLanguage(); updateModeText(); setOverlay('START'); requestAnimationFrame(frame);
})();
