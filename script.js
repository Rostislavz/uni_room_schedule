// ===================== Параметри =====================
const pairTimes = {
  1: '08:30 – 09:50',
  2: '10:05 – 11:25',
  3: '11:40 – 13:00',
  4: '13:15 – 14:35',
  5: '14:50 – 16:10',
  6: '16:25 – 17:45',
  7: '18:00 – 19:20',
  8: '19:30 – 20:50'
};

const fullDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
const fullDayNames = {
  'Пн': 'Понеділок',
  'Вт': 'Вівторок',
  'Ср': 'Середа',
  'Чт': 'Четвер',
  'Пт': 'Пʼятниця',
  'Сб': 'Субота'
};

const WEEK_TYPES = {
  NUMERATOR: 'чисельник',
  DENOMINATOR: 'знаменник',
  PERMANENT: 'постійно',
};

// Floor data cache with TTL (24 hours)
const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const floorDataCache = new Map(); // key → { promise, timestamp }

const PAGE_SIZE = 30; // rooms shown per page in Mode 1

let currentWeekFilter = 'all';
const dataRoot = (document.querySelector('meta[name="app-data-root"]')?.content || 'data').replace(/\/+$/, '');
let dataIndexPromise = null;

// ===================== DOM =====================
const mode1Btn = document.getElementById('mode1');
const mode2Btn = document.getElementById('mode2');
const controls = document.getElementById('controls');
const output = document.getElementById('output');

const setActiveMode = (modeId) => {
  mode1Btn.classList.toggle('active', modeId === 'mode1');
  mode2Btn.classList.toggle('active', modeId === 'mode2');
};

mode1Btn.addEventListener('click', () => { setActiveMode('mode1'); showMode1(); });
mode2Btn.addEventListener('click', () => { setActiveMode('mode2'); showMode2(); });
document.getElementById('week-all').addEventListener('click', () => setWeekFilter('all'));
document.getElementById('week-numerator').addEventListener('click', () => setWeekFilter('numerator'));
document.getElementById('week-denominator').addEventListener('click', () => setWeekFilter('denominator'));

document.addEventListener('DOMContentLoaded', () => {
  const embedded = window.self !== window.top;
  document.documentElement.classList.toggle('is-embedded', embedded);
  renderStaticSchedule();
  restoreScheduleAccordion();
  setActiveMode('mode1');
  showMode1();
});

// ===================== Загальні =====================
function setWeekFilter(filter) {
  currentWeekFilter = filter;
  document.querySelectorAll('.week-btn').forEach(btn => btn.classList.remove('active'));
  if (filter === 'all') document.getElementById('week-all').classList.add('active');
  if (filter === 'numerator') document.getElementById('week-numerator').classList.add('active');
  if (filter === 'denominator') document.getElementById('week-denominator').classList.add('active');
  refreshCurrentView();
}

function refreshCurrentView() {
  const activeMode = document.querySelector('.tab.active') || mode1Btn;
  if (activeMode?.id === 'mode1') {
    const buildingSelect = document.querySelector('select#Корпус');
    const floorSelect = document.querySelector('select#Поверх');
    const daySelect = document.querySelector('select#День');
    if (buildingSelect && daySelect) {
      renderFreeBusy(buildingSelect.value, floorSelect?.value || '', daySelect.value);
    }
  } else if (activeMode?.id === 'mode2') {
    const buildingSelect = document.querySelector('select#Корпус');
    const floorSelect = document.querySelector('select#Поверх');
    const roomSelect = document.querySelector('select#Аудиторія');
    if (buildingSelect && roomSelect) {
      renderCalendar(buildingSelect.value, floorSelect?.value || '', roomSelect.value);
    }
  }
}

function filterByWeek(entries) {
  const norm = (v) => (v || '').toString().trim().toLowerCase();
  if (currentWeekFilter === 'all') return entries;
  if (currentWeekFilter === 'numerator') {
    return entries.filter(e => {
      const t = norm(e['Тип тижня']);
      return t === WEEK_TYPES.NUMERATOR || t === WEEK_TYPES.PERMANENT;
    });
  }
  if (currentWeekFilter === 'denominator') {
    return entries.filter(e => {
      const t = norm(e['Тип тижня']);
      return t === WEEK_TYPES.DENOMINATOR || t === WEEK_TYPES.PERMANENT;
    });
  }
  return entries;
}

function pathPart(value) {
  return encodeURIComponent(String(value).trim());
}

async function loadDataIndex() {
  if (!dataIndexPromise) {
    dataIndexPromise = (async () => {
      const res = await fetch(`${dataRoot}/index.json`, { cache: 'no-cache' });
      if (!res.ok) throw new Error(`Cannot load data index (${res.status})`);
      const data = await res.json();
      updateFreshnessPill(data.generated_at);
      return data;
    })();
  }
  return dataIndexPromise;
}

function updateFreshnessPill(generatedAt) {
  const pill = document.getElementById('freshness-pill');
  if (!pill) return;
  if (!generatedAt) {
    pill.textContent = 'Офлайн режим';
    return;
  }
  const date = new Date(generatedAt);
  const now = new Date();
  const diffH = Math.round((now - date) / 3600000);
  const timeStr = date.toLocaleString('uk-UA', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  pill.textContent = diffH < 1 ? `Оновлено щойно (${timeStr})` : `Оновлено ${diffH} год тому (${timeStr})`;
  pill.title = `Дані згенеровано: ${timeStr}`;
}

function sortNatural(values) {
  return [...values].sort((a, b) => a.localeCompare(b, 'uk', { numeric: true }));
}

async function getBuildingList() {
  try {
    const index = await loadDataIndex();
    return sortNatural(index.buildings.map(b => b.id));
  } catch { return []; }
}

async function getFloors(building) {
  try {
    const index = await loadDataIndex();
    const b = index.buildings.find(b => b.id === building);
    if (!b) return [];
    return sortNatural(b.floors.map(f => f.id));
  } catch { return []; }
}

async function getRooms(building, floor) {
  try {
    const index = await loadDataIndex();
    const b = index.buildings.find(b => b.id === building);
    const f = b?.floors.find(f => f.id === floor);
    if (!f) return [];
    return sortNatural(f.rooms);
  } catch { return []; }
}

function getPairTime(n) { return pairTimes[n] || ''; }

function getWeekLabel(weekType) {
  if (weekType === WEEK_TYPES.NUMERATOR) return 'Ч';
  if (weekType === WEEK_TYPES.DENOMINATOR) return 'З';
  return '';
}

function getWeekClass(weekType) {
  if (weekType === WEEK_TYPES.NUMERATOR) return 'numerator';
  if (weekType === WEEK_TYPES.DENOMINATOR) return 'denominator';
  return '';
}

async function loadFloorData(building, floor) {
  const key = `${building}/${floor}`;
  const cached = floorDataCache.get(key);
  // Invalidate if older than TTL
  if (cached && (Date.now() - cached.timestamp) > CACHE_TTL_MS) {
    floorDataCache.delete(key);
  }
  if (!floorDataCache.has(key)) {
    const promise = (async () => {
      try {
        const res = await fetch(`${dataRoot}/floors/${pathPart(building)}/${pathPart(floor)}.json`);
        if (!res.ok) throw new Error(`Cannot load floor data (${res.status})`);
        return await res.json();
      } catch { return null; }
    })();
    floorDataCache.set(key, { promise, timestamp: Date.now() });
  }
  return floorDataCache.get(key).promise;
}

async function loadRoomData(building, floor, room) {
  const floorData = await loadFloorData(building, floor);
  if (!floorData?.rooms || !Array.isArray(floorData.rooms[room])) return [];
  return floorData.rooms[room];
}

// ===================== Режим 1 =====================
async function showMode1() {
  controls.innerHTML = '';
  output.innerHTML = '';
  const form = document.createElement('form');

  const buildingSelect = createSelect('Корпус');
  const floorSelect = createSelect('Поверх', [], true);
  const daySelect = createSelect('День', fullDays.map(d => ({ value: d, text: fullDayNames[d] })));

  const locationGroup = document.createElement('div');
  locationGroup.className = 'field-group two-cols';
  const locationLabel = document.createElement('p');
  locationLabel.className = 'group-label';
  locationLabel.textContent = 'Локація';
  locationGroup.append(locationLabel, labelWrap('Корпус', buildingSelect), labelWrap('Поверх', floorSelect));

  const timeGroup = document.createElement('div');
  timeGroup.className = 'field-group';
  const timeLabel = document.createElement('p');
  timeLabel.className = 'group-label';
  timeLabel.textContent = 'Час';
  timeGroup.append(timeLabel, labelWrap('День', daySelect));

  const actions = document.createElement('div');
  actions.className = 'actions';
  const button = document.createElement('button');
  button.textContent = 'Показати доступність';
  button.className = 'primary';
  const resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.textContent = 'Скинути фільтри';
  resetBtn.className = 'ghost';
  actions.append(button, resetBtn);

  form.append(locationGroup, timeGroup, actions);

  resetBtn.addEventListener('click', () => {
    populateBuildings(buildingSelect, floorSelect);
    daySelect.selectedIndex = 0;
    output.innerHTML = '';
  });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const building = buildingSelect.value;
    const floor = floorSelect.value;
    const day = daySelect.value;
    if (!building || !day) return;
    showLoading();
    try {
      await renderFreeBusy(building, floor, day);
    } catch { showError(); }
  });

  controls.appendChild(form);
  await populateBuildings(buildingSelect, floorSelect);
  if (buildingSelect.options.length === 0) {
    output.appendChild(buildEmptyState('Дані не згенеровано. Запустіть scripts/build_static_data.py'));
  }
}

async function renderFreeBusy(building, floor, selectedDay, page = 0) {
  const floors = floor ? [floor] : await getFloors(building);

  // Load all floor room data in parallel
  const floorRoomPairs = (await Promise.all(
    floors.map(async fl => {
      const rooms = await getRooms(building, fl);
      const roomData = await Promise.all(rooms.map(r => loadRoomData(building, fl, r)));
      return rooms.map((room, i) => ({ fl, room, data: roomData[i] }));
    })
  )).flat();

  const allPairNums = Object.keys(pairTimes).map(n => parseInt(n));
  const totalRooms = floorRoomPairs.length;
  const pageStart = page * PAGE_SIZE;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, totalRooms);
  const pageItems = floorRoomPairs.slice(pageStart, pageEnd);

  const table = document.createElement('table');
  table.classList.add('availability-table');
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  ['Аудиторія', 'Пара', 'Статус', 'Інформація'].forEach(text => {
    const th = document.createElement('th');
    th.textContent = text;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');

  const fragment = document.createDocumentFragment();
  for (const { room, data } of pageItems) {
    let entries = filterByWeek(data.filter(e => e.День === selectedDay));
    allPairNums.forEach((p, index) => {
      const entry = entries.find(e => e.Пара === p);
      const row = document.createElement('tr');

      if (index === 0) {
        const roomCell = document.createElement('td');
        roomCell.rowSpan = allPairNums.length;
        roomCell.textContent = room;
        row.appendChild(roomCell);
      }

      const statusClass = entry ? 'cell-busy' : 'cell-free';
      const pairCell = document.createElement('td');
      pairCell.className = statusClass;
      pairCell.textContent = `${p} (${getPairTime(p)})`;

      const statusCell = document.createElement('td');
      statusCell.className = statusClass;
      statusCell.textContent = entry ? 'Зайнято' : 'Вільно';

      const infoCell = buildInfoCell(entry, statusClass);
      row.append(pairCell, statusCell, infoCell);
      fragment.appendChild(row);
    });
  }
  tbody.appendChild(fragment);
  table.appendChild(tbody);

  output.innerHTML = '';

  if (!tbody.children.length) {
    output.appendChild(buildEmptyState());
    return;
  }

  // Filter state label
  const dayName = fullDayNames[selectedDay] || selectedDay;
  const floorLabel = floor ? ` · Поверх ${floor}` : '';
  const meta = document.createElement('p');
  meta.className = 'result-meta';
  meta.textContent = `Корпус ${building}${floorLabel} · ${dayName} · ${pageStart + 1}–${pageEnd} з ${totalRooms} аудиторій`;
  output.appendChild(meta);

  const wrap = document.createElement('div');
  wrap.className = 'table-wrap';
  wrap.appendChild(table);
  output.appendChild(wrap);

  // Pagination — "Load more" button
  if (pageEnd < totalRooms) {
    const loadMoreWrap = document.createElement('div');
    loadMoreWrap.className = 'load-more-wrap';
    const loadMoreBtn = document.createElement('button');
    loadMoreBtn.className = 'ghost';
    loadMoreBtn.textContent = `Показати ще (${totalRooms - pageEnd} залишилось)`;
    loadMoreBtn.addEventListener('click', async () => {
      showLoading();
      try { await renderFreeBusy(building, floor, selectedDay, page + 1); }
      catch { showError(); }
    });
    loadMoreWrap.appendChild(loadMoreBtn);
    output.appendChild(loadMoreWrap);
  }
}

function buildInfoCell(entry, statusClass) {
  const cell = document.createElement('td');
  cell.className = statusClass;
  if (entry) {
    const title = document.createElement('div');
    title.className = 'cell-title';
    title.textContent = entry.Предмет;
    const meta1 = document.createElement('div');
    meta1.className = 'cell-meta';
    meta1.textContent = entry.Викладач || '—';
    const meta2 = document.createElement('div');
    meta2.className = 'cell-meta';
    meta2.textContent = `${entry['Тип заняття']} · ${entry.Група}`;
    const weekLabel = getWeekLabel(entry['Тип тижня']);
    if (weekLabel) {
      const badge = document.createElement('span');
      badge.className = `week-badge ${getWeekClass(entry['Тип тижня'])}`;
      badge.textContent = weekLabel;
      badge.title = entry['Тип тижня'];
      meta2.appendChild(badge);
    }
    cell.append(title, meta1, meta2);
  } else {
    const freeTitle = document.createElement('div');
    freeTitle.className = 'cell-title free';
    freeTitle.textContent = 'Вільно';
    cell.appendChild(freeTitle);
  }
  return cell;
}

function buildEmptyState(message = 'Немає даних') {
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  empty.appendChild(document.createTextNode(message));
  empty.appendChild(document.createElement('br'));
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'ghost';
  button.textContent = 'Спробувати ще';
  button.addEventListener('click', () => location.reload());
  empty.appendChild(button);
  return empty;
}

function showLoading() {
  output.innerHTML = '';
  const el = document.createElement('div');
  el.className = 'empty-state';
  el.textContent = 'Завантаження...';
  output.appendChild(el);
}

function showError() {
  output.innerHTML = '';
  output.appendChild(buildEmptyState('Помилка завантаження даних.'));
}

// ===================== Режим 2 =====================
async function showMode2() {
  controls.innerHTML = '';
  output.innerHTML = '';
  const form = document.createElement('form');

  const buildingSelect = createSelect('Корпус');
  const floorSelect = createSelect('Поверх', [], true);
  const roomSelect = createSelect('Аудиторія', [], true);

  const locationGroup = document.createElement('div');
  locationGroup.className = 'field-group';
  const locationLabel = document.createElement('p');
  locationLabel.className = 'group-label';
  locationLabel.textContent = 'Локація';
  locationGroup.append(locationLabel, labelWrap('Корпус', buildingSelect), labelWrap('Поверх', floorSelect), labelWrap('Аудиторія', roomSelect));

  const actions = document.createElement('div');
  actions.className = 'actions';
  const button = document.createElement('button');
  button.textContent = 'Показати доступність';
  button.className = 'primary';
  const resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.textContent = 'Скинути фільтри';
  resetBtn.className = 'ghost';
  actions.append(button, resetBtn);

  form.append(locationGroup, actions);

  resetBtn.addEventListener('click', () => {
    populateBuildings(buildingSelect, floorSelect, roomSelect);
    output.innerHTML = '';
  });

  form.addEventListener('submit', async e => {
    e.preventDefault();
    showLoading();
    try {
      await renderCalendar(buildingSelect.value, floorSelect.value, roomSelect.value);
    } catch { showError(); }
  });

  controls.appendChild(form);
  await populateBuildings(buildingSelect, floorSelect, roomSelect);
  if (buildingSelect.options.length === 0) {
    output.appendChild(buildEmptyState('Дані не згенеровано. Запустіть scripts/build_static_data.py'));
  }
}

async function renderCalendar(building, floor, room) {
  const data = await loadRoomData(building, floor, room);
  const filteredData = filterByWeek(data);
  const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

  const table = document.createElement('table');
  table.classList.add('availability-table');
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  ['Пара', ...days].forEach(text => {
    const th = document.createElement('th');
    th.textContent = text;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  const fragment = document.createDocumentFragment();

  for (const p of Object.keys(pairTimes).map(n => parseInt(n))) {
    const row = document.createElement('tr');
    const pairCell = document.createElement('td');
    // #10 — show pair number and time inline, readable at a glance
    pairCell.textContent = `${p}`;
    const timeSpan = document.createElement('span');
    timeSpan.className = 'cell-meta';
    timeSpan.textContent = getPairTime(p);
    pairCell.appendChild(document.createElement('br'));
    pairCell.appendChild(timeSpan);
    row.appendChild(pairCell);

    for (const day of days) {
      const item = filteredData.find(e => e.День === day && e.Пара === p);
      row.appendChild(buildInfoCell(item, item ? 'cell-busy' : 'cell-free'));
    }
    fragment.appendChild(row);
  }
  tbody.appendChild(fragment);
  table.appendChild(tbody);

  output.innerHTML = '';

  // Filter state label
  const meta = document.createElement('p');
  meta.className = 'result-meta';
  meta.textContent = `Корпус ${building} · Поверх ${floor} · Аудиторія ${room}`;
  output.appendChild(meta);

  const wrap = document.createElement('div');
  wrap.className = 'table-wrap';
  wrap.appendChild(table);
  output.appendChild(tbody.children.length ? wrap : buildEmptyState());
}

// ===================== Select =====================
function createSelect(id, options = []) {
  const select = document.createElement('select');
  select.id = id;
  options.forEach(o => {
    const opt = document.createElement('option');
    opt.value = typeof o === 'object' ? o.value : o;
    opt.textContent = typeof o === 'object' ? o.text : o;
    select.appendChild(opt);
  });
  return select;
}

function labelWrap(text, select) {
  const label = document.createElement('label');
  label.textContent = text;
  label.htmlFor = select.id;
  label.appendChild(select);
  return label;
}

async function populateBuildings(buildingSelect, floorSelect, roomSelect = null) {
  const buildings = await getBuildingList();
  if (!buildings.length) return;
  buildingSelect.innerHTML = buildings.map(b => `<option value="${b}">${b}</option>`).join('');
  await populateFloors(buildings[0], floorSelect, roomSelect);
  buildingSelect.onchange = () => {
    if (buildingSelect.value) populateFloors(buildingSelect.value, floorSelect, roomSelect);
  };
}

async function populateFloors(building, floorSelect, roomSelect = null) {
  if (!building) return;
  const floors = await getFloors(building);
  floorSelect.disabled = !floors.length;
  if (!floors.length) return;
  floorSelect.innerHTML = floors.map(f => `<option value="${f}">${f}</option>`).join('');
  if (roomSelect) {
    await populateRooms(building, floors[0], roomSelect);
    floorSelect.onchange = () => {
      if (floorSelect.value) populateRooms(building, floorSelect.value, roomSelect);
    };
  }
}

async function populateRooms(building, floor, roomSelect) {
  const rooms = await getRooms(building, floor);
  roomSelect.disabled = !rooms.length;
  roomSelect.innerHTML = rooms.map(r => `<option value="${r}">${r}</option>`).join('');
}

// ===================== Розклад пар =====================
function renderStaticSchedule() {
  const scheduleBody = document.getElementById('schedule-body');
  const fragment = document.createDocumentFragment();
  Object.entries(pairTimes).forEach(([num, time]) => {
    const row = document.createElement('tr');
    const numCell = document.createElement('td');
    numCell.textContent = num;
    const timeCell = document.createElement('td');
    timeCell.textContent = time;
    row.append(numCell, timeCell);
    fragment.appendChild(row);
  });
  scheduleBody.appendChild(fragment);
}

// ===================== Accordion =====================
function restoreScheduleAccordion() {
  const trigger = document.querySelector('.accordion-trigger');
  const body = document.querySelector('.accordion-body');
  if (!trigger || !body) return;
  const saved = localStorage.getItem('scheduleAccordionOpen');
  const isOpen = saved === null ? true : saved === 'true';
  body.hidden = !isOpen;
  trigger.setAttribute('aria-expanded', String(isOpen));
  trigger.addEventListener('click', () => toggleAccordion(trigger, body));
  trigger.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleAccordion(trigger, body); }
  });
}

function toggleAccordion(trigger, body) {
  const next = body.hidden;
  body.hidden = !next;
  trigger.setAttribute('aria-expanded', String(next));
  localStorage.setItem('scheduleAccordionOpen', String(next));
}
