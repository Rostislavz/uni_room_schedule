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

  // Фільтр тижня: 'all' | 'numerator' | 'denominator'
  let currentWeekFilter = 'all';
  const dataRoot = (document.querySelector('meta[name="app-data-root"]')?.content || 'data').replace(/\/+$/, '');
  let dataIndexPromise = null;
  const floorDataCache = new Map();
  
  // ===================== DOM =====================
  const mode1Btn = document.getElementById('mode1');
  const mode2Btn = document.getElementById('mode2');

  const setActiveMode = (modeId) => {
    mode1Btn.classList.toggle('active', modeId === 'mode1');
    mode2Btn.classList.toggle('active', modeId === 'mode2');
  };

  mode1Btn.addEventListener('click', () => {
    setActiveMode('mode1');
    showMode1();
  });
  mode2Btn.addEventListener('click', () => {
    setActiveMode('mode2');
    showMode2();
  });
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
  
  const controls = document.getElementById('controls');
  const output = document.getElementById('output');
  
  // ===================== Загальні =====================
  function setWeekFilter(filter) {
    currentWeekFilter = filter;
    document.querySelectorAll('.week-btn').forEach(btn => btn.classList.remove('active'));
    if (filter === 'all') document.getElementById('week-all').classList.add('active');
    if (filter === 'numerator') document.getElementById('week-numerator').classList.add('active');
    if (filter === 'denominator') document.getElementById('week-denominator').classList.add('active');
    
    // Перерендерити таблицю при зміні фільтра
    refreshCurrentView();
  }

function refreshCurrentView() {
  const activeMode = document.querySelector('.tab.active') || mode1Btn;
  if (activeMode && activeMode.id === 'mode1') {
    const buildingSelect = document.querySelector('select#Корпус');
    const floorSelect = document.querySelector('select#Поверх');
    const daySelect = document.querySelector('select#День');
      if (buildingSelect && daySelect) {
        renderFreeBusy(buildingSelect.value, floorSelect?.value || '', daySelect.value);
      }
    } else if (activeMode && activeMode.id === 'mode2') {
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
      return t === 'чисельник' || t === 'постійно';
    });
  }
  if (currentWeekFilter === 'denominator') {
    return entries.filter(e => {
      const t = norm(e['Тип тижня']);
      return t === 'знаменник' || t === 'постійно';
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
        return await res.json();
      })();
    }
    return dataIndexPromise;
  }

  function sortNatural(values) {
    return [...values].sort((a, b) => a.localeCompare(b, 'uk', { numeric: true }));
  }

  async function getBuildingList() {
    try {
      const index = await loadDataIndex();
      return sortNatural(index.buildings.map(b => b.id));
    } catch {
      return [];
    }
  }

  async function getFloors(building) {
    try {
      const index = await loadDataIndex();
      const buildingEntry = index.buildings.find(b => b.id === building);
      if (!buildingEntry) return [];
      return sortNatural(buildingEntry.floors.map(f => f.id));
    } catch {
      return [];
    }
  }

  async function getRooms(building, floor) {
    try {
      const index = await loadDataIndex();
      const buildingEntry = index.buildings.find(b => b.id === building);
      const floorEntry = buildingEntry?.floors.find(f => f.id === floor);
      if (!floorEntry) return [];
      return sortNatural(floorEntry.rooms);
    } catch {
      return [];
    }
  }
  
  function getPairTime(n) {
    return pairTimes[n] || '';
  }
  
  function getWeekLabel(weekType) {
    if (weekType === 'чисельник') return 'Ч';
    if (weekType === 'знаменник') return 'З';
    return '';
  }

  function getWeekClass(weekType) {
    if (weekType === 'чисельник') return 'numerator';
    if (weekType === 'знаменник') return 'denominator';
    return '';
  }
  
  async function loadFloorData(building, floor) {
    const key = `${building}/${floor}`;
    if (!floorDataCache.has(key)) {
      const floorPromise = (async () => {
        try {
          const res = await fetch(`${dataRoot}/floors/${pathPart(building)}/${pathPart(floor)}.json`);
          if (!res.ok) throw new Error(`Cannot load floor data (${res.status})`);
          return await res.json();
        } catch {
          return null;
        }
      })();
      floorDataCache.set(key, floorPromise);
    }
    return floorDataCache.get(key);
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
  locationGroup.innerHTML = '<p class="group-label">Локація</p>';
  locationGroup.append(labelWrap('Корпус', buildingSelect));
  locationGroup.append(labelWrap('Поверх', floorSelect));

  const timeGroup = document.createElement('div');
  timeGroup.className = 'field-group';
  timeGroup.innerHTML = '<p class="group-label">Час</p>';
  timeGroup.append(labelWrap('День', daySelect));

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

    await renderFreeBusy(building, floor, day);
  });

  controls.appendChild(form);
  await populateBuildings(buildingSelect, floorSelect);
  if (buildingSelect.options.length === 0) {
    output.innerHTML = '';
    output.appendChild(buildEmptyState('Дані не згенеровано. Запустіть scripts/build_static_data.py'));
  }
}
  
async function renderFreeBusy(building, floor, selectedDay) {
    let floors = floor ? [floor] : await getFloors(building);
    const table = document.createElement('table');
    table.classList.add('availability-table');
    table.innerHTML = '<thead><tr><th>Аудиторія</th><th>Пара</th><th>Статус</th><th>Інформація</th></tr></thead><tbody></tbody>';
    const tbody = table.querySelector('tbody');
  
    for (const fl of floors) {
      const rooms = await getRooms(building, fl);
      for (const room of rooms) {
        const data = await loadRoomData(building, fl, room);
        let entries = data.filter(e => e.День === selectedDay);
        entries = filterByWeek(entries);
        const allPairs = Object.keys(pairTimes).map(n => parseInt(n));
  
        allPairs.forEach((p, index) => {
          const entry = entries.find(e => e.Пара === p);
          const row = document.createElement('tr');
  
          if (index === 0) {
            row.innerHTML += `<td rowspan="${allPairs.length}">${room}</td>`;
          }
  
          const statusClass = entry ? 'cell-busy' : 'cell-free';
          const statusText = entry ? 'Зайнято' : 'Вільно';

          const weekInfo = entry ? ` <span class="week-badge ${getWeekClass(entry['Тип тижня'])}">${getWeekLabel(entry['Тип тижня'])}</span>` : '';
  
          const info = entry
            ? `<div class="cell-title">${entry.Предмет}</div><div class="cell-meta">${entry.Викладач || '—'}</div><div class="cell-meta">${entry['Тип заняття']} · ${entry.Група}${weekInfo}</div>`
            : '<div class="cell-title free">Вільно</div>';
  
          row.innerHTML += `
            <td class="${statusClass}">${p} (${getPairTime(p)})</td>
            <td class="${statusClass}">${statusText}</td>
            <td class="${statusClass}">${info}</td>
          `;
  
          tbody.appendChild(row);
        });
      }
    }
  
    output.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'table-wrap';
    wrap.appendChild(table);
    output.appendChild(tbody.children.length ? wrap : buildEmptyState());
  }

  function buildEmptyState(message = 'Немає даних') {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.innerHTML = `${message}<br><button type="button" class="ghost" onclick="location.reload()">Спробувати ще</button>`;
    return empty;
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
  locationGroup.innerHTML = '<p class="group-label">Локація</p>';
  locationGroup.append(labelWrap('Корпус', buildingSelect));
  locationGroup.append(labelWrap('Поверх', floorSelect));
  locationGroup.append(labelWrap('Аудиторія', roomSelect));

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
    await renderCalendar(buildingSelect.value, floorSelect.value, roomSelect.value);
  });
  
    controls.appendChild(form);
    await populateBuildings(buildingSelect, floorSelect, roomSelect);
    if (buildingSelect.options.length === 0) {
      output.innerHTML = '';
      output.appendChild(buildEmptyState('Дані не згенеровано. Запустіть scripts/build_static_data.py'));
    }
  }
  
async function renderCalendar(building, floor, room) {
    const data = await loadRoomData(building, floor, room);
    let filteredData = filterByWeek(data);
    const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
    const table = document.createElement('table');
    table.classList.add('availability-table');
    table.innerHTML = '<thead><tr><th>Пара</th>' + days.map(d => `<th>${d}</th>`).join('') + '</tr></thead><tbody></tbody>';
    const tbody = table.querySelector('tbody');

    const allPairs = Object.keys(pairTimes).map(n => parseInt(n));

    for (let p of allPairs) {
      const row = document.createElement('tr');
      row.innerHTML = `<td>${p}<br><small>${getPairTime(p)}</small></td>` +
        days.map(day => {
          const item = filteredData.find(e => e.День === day && e.Пара === p);
          const weekBadge = item ? ` <span class="week-badge ${getWeekClass(item['Тип тижня'])}">${getWeekLabel(item['Тип тижня'])}</span>` : '';
          return `<td class="${item ? 'cell-busy' : 'cell-free'}">` +
            (item ? `<div class="cell-title">${item.Предмет}</div><div class="cell-meta">${item.Викладач || '—'}</div><div class="cell-meta">${item['Тип заняття']} · ${item.Група}${weekBadge}</div>` : '<div class="cell-title free">Вільно</div>') +
            '</td>';
        }).join('');
      tbody.appendChild(row);
    }
  
    output.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'table-wrap';
    wrap.appendChild(table);
    output.appendChild(tbody.children.length ? wrap : buildEmptyState());
  }
  
  // ===================== Select =====================
function createSelect(id, options = []) {
  const select = document.createElement('select');
  select.id = id;
  if (options.length) {
      options.forEach(o => {
        const opt = document.createElement('option');
        opt.value = typeof o === 'object' ? o.value : o;
        opt.textContent = typeof o === 'object' ? o.text : o;
        select.appendChild(opt);
      });
    }
    return select;
  }
  
function labelWrap(text, select) {
  const label = document.createElement('label');
  label.textContent = text;
  label.appendChild(select);
  return label;
}
  
  async function populateBuildings(buildingSelect, floorSelect, roomSelect = null) {
    const buildings = await getBuildingList();
    if (buildings.length === 0) return;

    buildingSelect.innerHTML = buildings.map(b => `<option value="${b}">${b}</option>`).join('');
    await populateFloors(buildings[0], floorSelect, roomSelect);

    buildingSelect.onchange = () => {
      const selected = buildingSelect.value;
      if (selected) {
        populateFloors(selected, floorSelect, roomSelect);
      }
    };
  }

  async function populateFloors(building, floorSelect, roomSelect = null) {
    if (!building) return;
    const floors = await getFloors(building);
    floorSelect.disabled = floors.length === 0;
    if (floors.length === 0) return;

    floorSelect.innerHTML = floors.map(f => `<option value="${f}">${f}</option>`).join('');

    if (roomSelect) {
      await populateRooms(building, floors[0], roomSelect);
      floorSelect.onchange = () => {
        const selectedFloor = floorSelect.value;
        if (selectedFloor) {
          populateRooms(building, selectedFloor, roomSelect);
        }
      };
    }
  }

  async function populateRooms(building, floor, roomSelect) {
    const rooms = await getRooms(building, floor);
    roomSelect.disabled = rooms.length === 0;
    roomSelect.innerHTML = rooms.map(r => `<option value="${r}">${r}</option>`).join('');
  }
  
// ===================== Розклад пар =====================
function renderStaticSchedule() {
  const scheduleBody = document.getElementById('schedule-body');
  Object.entries(pairTimes).forEach(([num, time]) => {
    const row = document.createElement('tr');
    row.innerHTML = `<td>${num}</td><td>${time}</td>`;
    scheduleBody.appendChild(row);
  });
}

// ===================== Accordion state =====================
function restoreScheduleAccordion() {
  const trigger = document.querySelector('.accordion-trigger');
  const body = document.querySelector('.accordion-body');
  if (!trigger || !body) return;
  const saved = localStorage.getItem('scheduleAccordionOpen');
  const isOpen = saved === null ? true : saved === 'true';
  body.hidden = !isOpen;
  trigger.setAttribute('aria-expanded', String(isOpen));
  trigger.addEventListener('click', () => toggleAccordion(trigger, body));
  trigger.addEventListener('keypress', (e) => { if (e.key === 'Enter') toggleAccordion(trigger, body); });
}

function toggleAccordion(trigger, body) {
  const next = body.hidden;
  body.hidden = !next;
  trigger.setAttribute('aria-expanded', String(next));
  localStorage.setItem('scheduleAccordionOpen', String(next));
}
