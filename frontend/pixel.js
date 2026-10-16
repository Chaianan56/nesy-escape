/* Game HUD and Interactive Detective Journal / Archive. Scene artwork is managed by GameArt. */
const PixelUI = (() => {
  const $ = id => document.getElementById(id);

  const rooms = [
    ['locomotive', 'หัวรถจักร', '01 · หัวรถจักร (ห้องเครื่องหวงห้าม)'],
    ['luggage_van_electrical', 'ระบบไฟฟ้า', '02 · ระบบไฟฟ้าและสัมภาระ'],
    ['dining_car_staff', 'ตู้เสบียง', '03 · ตู้เสบียงและห้องครัว'],
    ['first_class_car', 'ชั้นหนึ่ง', '04 · ชั้นหนึ่ง (ห้องเกิดเหตุ)'],
    ['lounge_car', 'เลานจ์', '05 · เลานจ์บาร์และที่พักผ่อน'],
    ['second_class_car', 'ชั้นสอง', '06 · ชั้นสอง (ตู้โดยสารทั่วไป)'],
  ];

  const IN_GAME_DOCUMENTS = [
    {
      id: "burnt_folder_c",
      imageEvidenceId: "burnt_folder_c",
      title: "เศษคำสั่งที่ถูกเผา (Burnt Memo BW-C/17)",
      date: "16 พฤศจิกายน 1923",
      classification: "ลับเฉพาะส่วนกลาง · สำเนาไฟไหม้บางส่วน",
      summary: "พบในถาดเขี่ยบุหรี่ห้องแคสเซียน ปรากฏรหัส [G.H.] สั่งแยกโทรเลขเตือนออกจากสำนวน",
      content: `เศษกระดาษพับซ้อนในถาดอ่านได้ว่า “BW-C/17 — 16 พฤศจิกายน 1923 — ให้แยกโทรเลขเตือนและคำให้การเรื่องคำสั่งส่วนกลางออกจากชุดสอบสวน...” และส่วนลงนาม G.H. ส่วนอื่นไหม้จนอ่านไม่ได้ เลขเอกสารสามารถเทียบสารบัญในกระเป๋าได้\n\nรอยไหม้อยู่ตามขอบและรอยพับ ไม่มีข้อความส่วนที่หายไปให้เดาเติม การระบุผู้ลงนามต้องตรวจเทียบเลขเอกสารกับทะเบียนในกระเป๋าสำนวน`,
    },
    {
      id: "autopsy_report",
      imageEvidenceId: "liora_patient_log",
      title: "บันทึกตรวจร่างเบื้องต้น (Autopsy Report)",
      date: "14 พฤศจิกายน 1938 · 21:20 น.",
      classification: "รายงานชันสูตรเบื้องต้น · แพทย์ประจำขบวน",
      summary: "แพทย์หญิงลิโอรา เวนน์ ตรวจพบแผลของมีคม เลือดเริ่มเย็นตัวก่อนฮีตเตอร์ดับ",
      content: `14 พฤศจิกายน 1938 หลังพบร่างราว 21:20 — ผู้ตรวจ: ลิโอรา เวนน์\n\nพบบาดแผลจากของคมและร่องรอยต่อสู้ มีดเปิดจดหมายใกล้ร่างสอดคล้องกับลักษณะอาวุธที่ต้องตรวจเพิ่มเติม ยังไม่มีผลตรวจลายนิ้วมือหรือผลห้องปฏิบัติการบนขบวน\n\nการตรวจครั้งนี้ไม่ระบุเวลาตายเป็นนาทีหรือยืนยันว่าเสียชีวิตขณะไฟดับ ผู้สืบสวนต้องตรวจลำดับเหตุการณ์จากฉากและพยานร่วมกัน`,
    },
    {
      id: "secret_file",
      imageEvidenceId: "secret_file",
      title: "แฟ้มรักษาและคำให้การเอเลียส เวนน์ (Project Nocturne)",
      date: "14 พฤศจิกายน 1923 – 1931",
      classification: "เวชระเบียนส่วนบุคคล · คำให้การที่ถูกตัดออก",
      summary: "บิดาของลิโอราให้การเรื่องคำสั่งส่วนกลางให้เดินรถต่อแม้มีคำเตือน",
      content: `เอเลียส เวนน์ รอดจากเหตุ 14 พฤศจิกายน 1923 เขาให้การระหว่างรักษาว่ามีคำเตือนก่อนออกขบวนและมีคำสั่งให้เดินต่อ คำให้การนี้ไม่อยู่ในสำนวนเผยแพร่ บันทึกสุดท้ายระบุเสียชีวิตด้วยโรคประจำตัวในสถานบำบัดปี 1931 ลิโอราเก็บแฟ้มเพื่อคืนความน่าเชื่อถือให้พ่อ ไม่ได้เป็นหลักฐานว่าผู้ใดฆ่าแคสเซียนคืนนี้\n\nสำเนาคำให้การระหว่างพักรักษา: “เราได้รับคำเตือนให้รอยืนยันเส้นทาง แต่มีคำสั่งจากส่วนกลางให้เดินต่อ”\n\nเอกสารแนบระบุว่าคำให้การนี้ถูกนำออกจากสำนวนฉบับเผยแพร่ แฟ้มไม่มีข้อมูลว่าใครอยู่ในห้องแคสเซียนคืนนี้`,
    },
    {
      id: "dossier_missing_file_c",
      imageEvidenceId: "dossier_missing_file_c",
      title: "สำเนาโทรเลขเตือนจากเบลล์เวเธอร์ (Voss Telegram Draft)",
      date: "14 พฤศจิกายน 1923",
      classification: "ร่างโทรเลขสถานีรถไฟเบลล์เวเธอร์",
      summary: "นายสถานีแอนเซลม์ วอสส์ ขอให้หยุดขบวนพิเศษก่อนเกิดโศกนาฏกรรม",
      content: `14 พฤศจิกายน 1923\nจาก แอนเซลม์ วอสส์ นายสถานีเบลล์เวเธอร์\n\nขอให้หยุดรอการยืนยันว่าเส้นทางปลอดภัยก่อนปล่อยขบวนพิเศษ Nocturne\n\nสำเนาอยู่ในแฟ้ม B ร่วมกับสมุดบันทึกต้นฉบับของนายสถานีที่มาราให้แคสเซียนยืมตรวจ เลขรับส่งใช้เทียบทะเบียน ไม่ใช่คำยืนยันว่าใครสังหารแคสเซียนในปี 1938`,
    }
  ];

  let data = null, activeTab = 'evidence', revision = 0;

  function button(label, command, className = 'object-button') {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = className;
    b.textContent = label;
    b.onclick = () => {
      document.getElementById('casebookDialog')?.close();
      document.getElementById('archiveDetailDialog')?.close();
      fillInput(command);
    };
    return b;
  }

  function empty(title, text) {
    const box = document.createElement('div');
    box.className = 'empty-state';
    const icon = document.createElement('div');
    icon.className = 'empty-icon';
    icon.textContent = '◇';
    const heading = document.createElement('strong');
    heading.textContent = title;
    const p = document.createElement('p');
    p.textContent = text;
    box.append(icon, heading, p);
    return box;
  }

  function imageSlot(kind, id, label, interactive = true) {
    const slot = document.createElement(interactive ? 'button' : 'div');
    if (interactive) slot.type = 'button';
    slot.className = `archive-image-slot archive-image-slot-${kind}`;
    slot.dataset.imageSlot = `${kind}:${id}`;
    if (!interactive) slot.setAttribute('role', 'img');
    slot.setAttribute('aria-label', `ช่องภาพสำหรับ${label}`);
    const artImage = kind === 'evidence' && typeof GameArt !== 'undefined' && GameArt.journalImage
      ? GameArt.journalImage(id, label)
      : kind === 'person' && typeof GameArt !== 'undefined' && GameArt.journalPersonImage
        ? GameArt.journalPersonImage(id, label)
        : null;
    const mark = document.createElement('span');
    mark.setAttribute('aria-hidden', 'true');
    mark.textContent = '▧';
    const caption = document.createElement('small');
    caption.textContent = 'พื้นที่ใส่ภาพ';
    if (artImage) {
      artImage.classList.add('archive-slot-image');
      artImage.addEventListener('load', () => { mark.hidden = true; caption.hidden = true; }, {once:true});
      slot.append(artImage);
    }
    slot.append(mark, caption);
    return slot;
  }

  function makeCardClickable(card, onActivate, label) {
    card.classList.add('archive-card-clickable');
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-label', label);
    card.addEventListener('click', event => {
      if (event.target.closest('button, a, input, select, textarea')) return;
      onActivate();
    });
    card.addEventListener('keydown', event => {
      if (event.target !== card || (event.key !== 'Enter' && event.key !== ' ')) return;
      event.preventDefault();
      onActivate();
    });
  }

  function showArchiveDetail({kind, id, title, subtitle, description, sections = [], actions = []}) {
    let dialog = $('archiveDetailDialog');
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.id = 'archiveDetailDialog';
      dialog.className = 'archive-detail-dialog';
      dialog.innerHTML = `<header class="archive-detail-header"><div><span class="eyebrow">DETECTIVE’S ARCHIVE</span><h2></h2><p></p></div><button type="button" class="history-close">✕ ปิด</button></header><div class="archive-detail-body"></div><footer class="archive-detail-actions"></footer>`;
      document.body.append(dialog);
      dialog.querySelector('.history-close').onclick = () => dialog.close();
      dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    }
    dialog.querySelector('h2').textContent = title;
    dialog.querySelector('.archive-detail-header p').textContent = subtitle || '';
    const body = dialog.querySelector('.archive-detail-body');
    body.replaceChildren();
    body.append(imageSlot(kind, id, title, false));
    if (description) {
      const paragraph = document.createElement('p');
      paragraph.className = 'archive-detail-description';
      paragraph.textContent = description;
      body.append(paragraph);
    }
    sections.forEach(section => {
      const block = document.createElement('section');
      block.className = 'archive-detail-section';
      const heading = document.createElement('strong');
      heading.textContent = section.title;
      const text = document.createElement('p');
      text.textContent = section.text;
      block.append(heading, text);
      body.append(block);
    });
    const footer = dialog.querySelector('.archive-detail-actions');
    footer.replaceChildren();
    actions.forEach(item => footer.append(button(item.label, item.command, 'chip-btn')));
    if (!dialog.open) dialog.showModal();
  }

  function openEvidenceDetail(evidence) {
    showArchiveDetail({
      kind: 'evidence', id: evidence.id, title: evidence.name,
      subtitle: `${evidence.kind === 'testimony' ? 'คำให้การ' : 'วัตถุพยาน'} · ${evidence.source || ''}`,
      description: evidence.description,
      sections: evidence.source_note ? [{title: 'บันทึกแหล่งที่มา', text: evidence.source_note}] : [],
    });
  }

  function openPersonDetail(person) {
    const personName = person.name.split(' (')[0];
    const testimonies = data.evidence.filter(item => item.kind === 'testimony' && (
      item.source?.includes(personName) || item.source_note?.includes(personName) ||
      (person.id && item.id?.includes(person.id.split('_')[0]))
    ));
    const role = person.accusable === false ? 'พยาน / บุคลากร' : 'ผู้ต้องสงสัย';
    const location = locationsMap[person.location] || person.location || 'บนขบวน';
    const actions = [];
    if (person.here && !(typeof gameOver !== 'undefined' && gameOver)) {
      actions.push({label: `สอบปากคำ ${personName}`, command: `สอบปากคำ ${personName}`});
      (person.topics || []).forEach(topic => actions.push({
        label: `ถามเรื่อง${topic.label}`, command: `ถาม${personName} เรื่อง${topic.label}`,
      }));
    } else if (person.location && !(typeof gameOver !== 'undefined' && gameOver)) {
      actions.push({label: `ไปพบที่ ${location}`, command: `ไปที่ ${person.location}`});
    }
    const sections = [
      {title: 'สถานะการสืบสวน', text: `${role} · ${person.interrogated ? 'เคยสนทนาแล้ว' : 'ยังไม่ได้สนทนา'}`},
    ];
    if (testimonies.length) sections.push({
      title: `คำให้การที่บันทึกไว้ (${testimonies.length})`,
      text: testimonies.map(item => `${item.description}\n— ${item.name}`).join('\n\n'),
    });
    showArchiveDetail({kind: 'person', id: person.id, title: person.name, subtitle: location, sections, actions});
  }

  function drawScene(location) {
    if (typeof GameArt !== 'undefined' && GameArt.sync) {
      GameArt.sync(gameState || { current_location: location });
    }
  }

  // Interactive Train Map
  function map() {
    const wrap = $('trainCars');
    if (!wrap) return;
    const currentLocation = gameState?.current_location;
    const currentRoom = rooms.find(([id]) => id === currentLocation);
    const currentLabel = currentRoom?.[1] || currentRoom?.[2] || 'ไม่ทราบตำแหน่ง';
    const currentLocationLabel = $('mapCurrentLocation');
    if (currentLocationLabel) currentLocationLabel.textContent = currentLabel;

    const passengerCar = (x, index) => {
      const [id, label] = rooms[index];
      const active = currentLocation === id;
      const shell = active ? 'active-shell' : 'car-shell';
      const roof = active ? 'active-roof' : 'car-roof';
      const window = active ? 'train-window-active' : 'train-window';
      const sideStroke = active ? '#e6bd70' : '#9e7844';
      return `<g class="train-svg-car${active ? ' active' : ''}" data-room-index="${index}" transform="translate(${x} 0)">
        <path class="${shell}" d="M6 48h183l12 9v21H0V57z"/><path class="${roof}" d="M12 48l12-10h147l14 10z"/>
        <path d="M8 52v25m181-25v25" fill="none" stroke="${sideStroke}" stroke-width="2"/>
        <use href="#${window}" x="21" y="52"/><use href="#${window}" x="52" y="52"/><use href="#${window}" x="83" y="52"/><use href="#${window}" x="114" y="52"/><use href="#${window}" x="145" y="52"/>
        <use href="#train-wheel${active ? '-active' : ''}" x="38" y="83"/><use href="#train-wheel${active ? '-active' : ''}" x="164" y="83"/>
        <rect class="train-hit" x="-3" y="27" width="208" height="70" aria-hidden="true"/>
        ${active ? '<path class="train-position-pin" d="M103 5l-10 15h7v10h6V20h7z" aria-hidden="true"/>' : ''}
      </g>`;
    };

    const svg = `<svg class="train-map-svg" viewBox="0 0 1320 106" role="group" aria-label="แผนผังตู้รถไฟ เลือกตู้เพื่อเดินทาง">
      <defs>
        <g id="train-wheel"><circle class="train-wheel" r="11"/><circle class="train-wheel-hub" r="3"/></g>
        <g id="train-wheel-active"><circle class="train-wheel active-wheel" r="11"/><circle class="train-wheel-hub active-hub" r="3"/></g>
        <g id="train-window"><rect class="train-window" width="25" height="21" rx="2"/><path class="train-window-glint" d="M5 4v14"/></g>
        <g id="train-window-active"><rect class="train-window active-window" width="25" height="21" rx="2"/><path class="train-window-glint" d="M5 4v14"/></g>
      </defs>
      <path class="train-rail" d="M12 94H1308M12 101H1308"/>
      <path class="train-sleepers" d="M28 91v13M72 91v13M116 91v13M160 91v13M204 91v13M248 91v13M292 91v13M336 91v13M380 91v13M424 91v13M468 91v13M512 91v13M556 91v13M600 91v13M644 91v13M688 91v13M732 91v13M776 91v13M820 91v13M864 91v13M908 91v13M952 91v13M996 91v13M1040 91v13M1084 91v13M1128 91v13M1172 91v13M1216 91v13M1260 91v13"/>
      <path class="train-coupler" d="M194 77h29M419 77h27M642 77h27M865 77h27M1088 77h27"/>
      <g class="train-svg-car${currentLocation === rooms[0][0] ? ' active' : ''}" data-room-index="0">
        <path class="train-metal" d="M20 77h18l13-11h20V48h24V40h55v8h32v22l20 7v8H20z"/>
        <path class="train-car-roof" d="M91 40V31h59v9"/><rect class="train-window${currentLocation === rooms[0][0] ? ' active-window' : ''}" x="102" y="43" width="34" height="21" rx="2"/>
        <path class="train-metal" d="M42 52h56v23H42zM48 46h47v5H48zM58 41h31v5H58z"/><rect class="train-metal" x="61" y="23" width="11" height="24"/><path class="train-metal" d="M58 23h17l-3-6H61z"/>
        <circle class="train-headlamp" cx="30" cy="63" r="4"/><path class="train-metal" d="M20 77h-7l11 9h22l-9-9"/>
        <use href="#train-wheel${currentLocation === rooms[0][0] ? '-active' : ''}" x="61" y="83"/><use href="#train-wheel${currentLocation === rooms[0][0] ? '-active' : ''}" x="113" y="83"/><use href="#train-wheel${currentLocation === rooms[0][0] ? '-active' : ''}" x="169" y="83"/>
        <path class="train-engine-rod" d="M61 83h108"/><rect class="train-hit" x="10" y="14" width="200" height="82" aria-hidden="true"/>
        ${currentLocation === rooms[0][0] ? '<path class="train-position-pin" d="M104 5l-10 15h7v10h6V20h7z" aria-hidden="true"/>' : ''}
      </g>
      ${passengerCar(218, 1)}${passengerCar(441, 2)}${passengerCar(664, 3)}${passengerCar(887, 4)}${passengerCar(1110, 5)}
    </svg>`;
    wrap.replaceChildren();
    wrap.classList.add('train-cars-rendered');
    wrap.insertAdjacentHTML('beforeend', svg);

    const activateRoom = index => {
      if (typeof gameOver !== 'undefined' && gameOver) return;
      const [id] = rooms[index];
      fillInput(currentLocation === id ? 'ดูรอบๆ' : `ไปตู้ ${index + 1}`);
    };
    wrap.querySelectorAll('.train-svg-car').forEach(car => {
      const index = Number(car.dataset.roomIndex);
      const [id, label] = rooms[index];
      const current = currentLocation === id;
      car.setAttribute('role', 'button');
      car.setAttribute('tabindex', typeof gameOver !== 'undefined' && gameOver ? '-1' : '0');
      car.setAttribute('aria-label', `${index === 0 ? 'หัวรถจักร' : `ตู้ ${label}`} · ${rooms[index][2]}${current ? ' · ตำแหน่งปัจจุบัน' : ''}`);
      if (current) car.setAttribute('aria-current', 'location');
      if (typeof gameOver !== 'undefined' && gameOver) car.setAttribute('aria-disabled', 'true');
      car.addEventListener('click', () => activateRoom(index));
      car.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          activateRoom(index);
        }
      });
    });

    const stops = document.createElement('div');
    stops.className = 'train-map-stops';
    rooms.forEach(([id, label], i) => {
      const isCurrent = gameState?.current_location === id;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'train-map-stop' + (isCurrent ? ' active' : '');
      b.title = isCurrent ? `คุณยืนอยู่ที่นี่: ${label}` : `คลิกเพื่อเดินทางไปที่ ${label}`;
      b.setAttribute('aria-label', i === 0 ? 'หัวรถจักร พื้นที่หวงห้าม' : `ตู้ ${label}`);
      if (isCurrent) b.setAttribute('aria-current', 'location');
      const name = document.createElement('span');
      name.className = 'train-map-stop-name';
      name.textContent = label;
      const subtitle = document.createElement('small');
      subtitle.textContent = ['ห้องเครื่อง','สัมภาระ','ห้องครัว','ห้องเกิดเหตุ','เลานจ์บาร์','ตู้โดยสาร'][i];
      name.append(subtitle);
      b.append(name);
      b.onclick = () => {
        if (typeof gameOver !== 'undefined' && gameOver) return;
        fillInput(isCurrent ? 'ดูรอบๆ' : `ไปตู้ ${i + 1}`);
      };
      b.disabled = typeof gameOver !== 'undefined' && gameOver;
      stops.append(b);
    });
    wrap.append(stops);
  }

  // Case Board
  function board() {
    const wrap = $('pillarBoard');
    if (!wrap) return;
    wrap.replaceChildren();
    if (!data) return;

    if (!data.case_closed) {
      wrap.append(empty('สี่เสาหลักฐาน', 'รวบรวมเวลา แรงจูงใจ โอกาส และข้อหักล้างเพื่อประกอบข้อสรุป'));
      return;
    }

    const select = $('suspectSelect');
    const selectedSuspect = select ? select.value : Object.keys(data.pillars || {})[0];
    const status = (data.pillars && data.pillars[selectedSuspect]) || {};

    Object.entries(data.pillar_labels || {}).forEach(([id, label]) => {
      const yes = (status[id] || []).length > 0;
      const row = document.createElement('div');
      row.className = 'pillar-row';
      const line = document.createElement('div');
      const l = document.createElement('span');
      l.textContent = label;
      const r = document.createElement('span');
      r.className = yes ? 'pillar-ready' : 'pillar-missing';
      r.textContent = yes ? '✓ มีข้อสรุป' : 'ยังไม่ครบ';
      line.append(l, r);
      const p = document.createElement('progress');
      p.max = 1;
      p.value = yes ? 1 : 0;
      p.setAttribute('aria-label', label);
      row.append(line, p);
      wrap.append(row);
    });
  }

  // Open Document Modal Reader
  function openDocument(doc) {
    const discoveredIds = new Set((data?.evidence || []).map(item => item.id));
    if (!discoveredIds.has(doc.id) && !discoveredIds.has(doc.imageEvidenceId)) return;
    const dialog = $('documentDialog');
    if (!dialog) return;
    $('docTitle').textContent = doc.title;
    $('docDate').textContent = doc.date;
    $('docBadge').textContent = doc.classification;
    $('docBody').innerHTML = `<div class="doc-text-body">${doc.content.replace(/\n\n/g, '<br><br>')}</div>`;
    dialog.showModal();
  }

  // Render Tab 1: Chat History
  function renderChatTab(wrap) {
    const feed = $('chatFeed');
    if (!feed || !feed.children.length) {
      wrap.append(empty('ยังไม่มีประวัติการคุย', 'พิมพ์คำสั่งสืบสวนหรือกดสำรวจตรงหน้า บันทึกการสนทนาจะปรากฏที่นี่'));
      return;
    }

    const header = document.createElement('div');
    header.className = 'archive-tab-header';
    header.innerHTML = `
      <div class="archive-headline">
        <strong>บันทึกบทสนทนาและคำสั่ง</strong>
        <small>${feed.children.length} ข้อความ</small>
      </div>
      <button type="button" class="chip-btn scroll-latest-btn" id="scrollTabLatest">ไปล่าสุด ↓</button>
    `;
    wrap.append(header);

    const logContainer = document.createElement('div');
    logContainer.className = 'archive-chat-log';

    Array.from(feed.children).forEach((node, idx) => {
      if (node.id === 'initLoading') return;
      const item = document.createElement('div');
      item.className = 'archive-chat-item ' + (node.className || '');

      const isUser = node.classList.contains('msg-user');
      const isError = node.classList.contains('msg-error');

      const roleBadge = document.createElement('div');
      roleBadge.className = 'archive-msg-meta';
      roleBadge.textContent = isUser ? `🕵️ คำสั่งที่ #${idx + 1}` : (isError ? `⚠️ ข้อผิดพลาด` : `📜 การสืบสวน`);
      item.append(roleBadge);

      const contentClone = node.cloneNode(true);
      // Clean up internal buttons from interfering
      contentClone.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
        });
      });
      item.append(contentClone);
      logContainer.append(item);
    });

    wrap.append(logContainer);

    header.querySelector('#scrollTabLatest')?.addEventListener('click', () => {
      logContainer.scrollTo({ top: logContainer.scrollHeight, behavior: 'smooth' });
    });
  }

  // Render Tab 2: Items & Documents
  function renderEvidenceTab(wrap) {
    // 1. Carried Inventory
    if (data.inventory?.length) {
      const invSection = document.createElement('div');
      invSection.className = 'archive-section';
      invSection.innerHTML = `<h3 class="archive-section-title">🎒 สิ่งของที่พกติดตัว (${data.inventory.length})</h3>`;
      const invList = document.createElement('div');
      invList.className = 'inventory-grid';
      data.inventory.forEach(item => {
        const chip = document.createElement('div');
        chip.className = 'inventory-item-card';
        const image = item.id && typeof GameArt !== 'undefined' && GameArt.journalImage
          ? GameArt.journalImage(item.id, item.name)
          : null;
        if (image) {
          image.classList.add('inventory-item-image');
          chip.append(image);
        }
        const name = document.createElement('strong');
        name.textContent = item.name;
        const description = document.createElement('small');
        description.textContent = item.description || '';
        chip.append(name, description);
        invList.append(chip);
      });
      invSection.append(invList);
      wrap.append(invSection);
    }

    // 2. In-game Documents & Memos
    const docSection = document.createElement('div');
    docSection.className = 'archive-section';
    docSection.innerHTML = `<h3 class="archive-section-title">📜 เอกสารและแฟ้มลับที่พบ</h3>`;

    const discoveredIds = new Set(data.evidence.map(e => e.id));
    let foundDocCount = 0;

    IN_GAME_DOCUMENTS.forEach(doc => {
      // Match a document to the evidence that actually unlocks its image.
      // Some display IDs (for example autopsy_report) differ from evidence IDs.
      const isFound = discoveredIds.has(doc.id) || discoveredIds.has(doc.imageEvidenceId);
      if (!isFound) return;
      foundDocCount++;
      const card = document.createElement('div');
      card.className = 'doc-card doc-found';
      card.innerHTML = `
        <div class="doc-card-top"><span class="doc-card-badge">พบแล้ว</span></div>
        <strong class="doc-card-title"></strong>
        <small class="doc-card-date"></small>
      `;
      card.querySelector('.doc-card-title').textContent = doc.title;
      card.querySelector('.doc-card-date').textContent = doc.date;
      makeCardClickable(card, () => openDocument(doc), `เปิดรายละเอียด${doc.title}`);
      if (discoveredIds.has(doc.imageEvidenceId)) {
        const image = imageSlot('evidence', doc.imageEvidenceId, doc.title, false);
        image.classList.add('doc-card-image-slot');
        image.setAttribute('aria-label', `เปิดรายละเอียด${doc.title}`);
        card.querySelector('.doc-card-top').after(image);
      } else {
        const image = imageSlot('evidence', doc.id, doc.title, false);
        image.classList.add('doc-card-image-slot');
        image.setAttribute('aria-label', `เปิดรายละเอียด${doc.title}`);
        card.querySelector('.doc-card-top').after(image);
      }
      docSection.append(card);
    });

    // Also include any unlocked case backgrounds
    (data.background || []).forEach(entry => {
      const bgCard = document.createElement('div');
      bgCard.className = 'doc-card doc-found';
      bgCard.innerHTML = `
        <div class="doc-card-top"><span class="doc-card-badge">บันทึกเบื้องหลัง</span></div>
        <strong class="doc-card-title">${entry.title}</strong>
        <p class="doc-card-summary">${entry.text}</p>
      `;
      docSection.append(bgCard);
    });

    if (!foundDocCount && !data.background?.length) {
      docSection.append(empty('ยังไม่พบเอกสารหรือแฟ้มลับ', 'ค้นหาวัตถุพยานหรือสอบถามบุคคลเพื่อปลดล็อกเอกสารในแฟ้ม'));
    }

    wrap.append(docSection);

    // 3. Physical Evidence
    const clueSection = document.createElement('div');
    clueSection.className = 'archive-section';
    clueSection.innerHTML = `<h3 class="archive-section-title">🔍 วัตถุพยานและหลักฐานที่พบ (${data.evidence.length} ชิ้น)</h3>`;

    if (!data.evidence.length) {
      clueSection.append(empty('ยังไม่พบหลักฐาน', 'สำรวจห้อง ตรวจสิ่งของ และสอบถามพยานเพื่อบันทึกหลักฐาน'));
    } else {
      const evidenceGrid = document.createElement('div');
      evidenceGrid.className = 'evidence-grid';
      data.evidence.forEach((e, i) => {
        const box = document.createElement('article');
        box.className = 'evidence-card archive-evidence-card';
        const image = imageSlot('evidence', e.id, e.name, false);
        makeCardClickable(box, () => openEvidenceDetail(e), `เปิดรายละเอียดหลักฐาน: ${e.name}`);
        const title = document.createElement('div');
        title.className = 'archive-evidence-title-row';
        const icon = document.createElement('span');
        icon.className = 'clue-icon';
        icon.textContent = String(i + 1).padStart(2, '0');
        const name = document.createElement('span');
        name.className = 'archive-evidence-name';
        name.textContent = e.name;
        title.append(name, icon);
        box.append(image, title);

        evidenceGrid.append(box);
      });
      clueSection.append(evidenceGrid);
    }
    wrap.append(clueSection);

    // 4. Inference Questions & Pending Claims
    if (data.inference_questions?.length || data.scene_followups?.length || data.validated_claims?.length) {
      const claimSection = document.createElement('div');
      claimSection.className = 'archive-section';
      claimSection.innerHTML = `<h3 class="archive-section-title">💡 ข้อสรุปและประเด็นที่ต้องเชื่อมโยง</h3>`;

      (data.scene_followups || []).forEach(item => {
        const box = document.createElement('div');
        box.className = 'case-question scene-followup';
        const title = document.createElement('strong');
        title.textContent = `มีประเด็นใหม่กับ ${item.person_name}`;
        const here = gameState?.current_location === item.location;
        const action = button(
          here ? `ถามต่อ: ${item.label}` : `ไปพบที่ ${locationsMap[item.location] || item.location}`,
          here ? `ถาม${item.person_name} เรื่อง${item.label}` : `ไปที่ ${item.location}`
        );
        action.disabled = typeof gameOver !== 'undefined' && gameOver;
        box.append(title, action);
        claimSection.append(box);
      });

      (data.inference_questions || []).forEach(q => {
        const box = document.createElement('div');
        box.className = 'case-question';
        const title = document.createElement('strong');
        title.textContent = q.prompt;
        const action = document.createElement('button');
        action.type = 'button';
        action.className = 'object-button highlight-btn';
        action.textContent = 'เสนอข้อสรุปและแนบหลักฐาน';
        action.onclick = () => {
          if (typeof InferenceUI !== 'undefined') InferenceUI.open(q, data.evidence);
        };
        action.disabled = typeof gameOver !== 'undefined' && gameOver;
        box.append(title, action);
        claimSection.append(box);
      });

      (data.validated_claims || []).forEach(claim => {
        const note = document.createElement('div');
        note.className = 'note note-validated';
        note.innerHTML = `<strong>✓ ข้อสรุปที่คุณตรวจสอบแล้ว:</strong> ${claim.name}`;
        claimSection.append(note);
      });

      wrap.append(claimSection);
    }
  }

  // Render Tab 3: People & Testimonies
  function renderPeopleTab(wrap) {
    if (!data.people || !data.people.length) {
      wrap.append(empty('ยังไม่พบบุคคล', 'เดินทางไปตู้ต่าง ๆ เพื่อพบกับผู้โดยสารและพยาน'));
      return;
    }

    const header = document.createElement('div');
    header.className = 'archive-tab-header';
    header.innerHTML = `
      <div class="archive-headline">
        <strong>บุคคลบนขบวนรถไฟ</strong>
        <small>${data.people.length} คน</small>
      </div>
    `;
    wrap.append(header);

    const peopleGrid = document.createElement('div');
    peopleGrid.className = 'people-grid';
    data.people.forEach(p => {
      const card = document.createElement('div');
      card.className = 'person-card' + (p.here ? ' person-here' : '');
      const personName = p.name.split(' (')[0];
      const testimonies = data.evidence.filter(e => e.kind === 'testimony' && (
        e.source?.includes(personName) || e.source_note?.includes(personName) ||
        (p.id && e.id?.includes(p.id.split('_')[0]))
      ));
      const image = imageSlot('person', p.id, p.name, false);
      makeCardClickable(card, () => openPersonDetail(p), `เปิดข้อมูลบุคคล: ${p.name}`);
      card.append(image);

      const top = document.createElement('div');
      top.className = 'person-top';
      const name = document.createElement('strong');
      name.className = 'person-name';
      name.textContent = p.name;

      const badge = document.createElement('span');
      badge.className = 'person-badge ' + (p.here ? 'badge-here' : 'badge-away');
      badge.textContent = p.here ? '📍 อยู่ในตู้นี้' : (locationsMap[p.location] || p.location || 'บนขบวน');

      top.append(name, badge);
      card.append(top);
      const hint = document.createElement('small');
      hint.className = 'person-card-hint';
      hint.textContent = testimonies.length ? `มีข้อมูล/คำให้การ ${testimonies.length} รายการ · กดรูปเพื่อดู` : 'กดรูปเพื่อดูข้อมูล';
      card.append(hint);

      peopleGrid.append(card);
    });
    wrap.append(peopleGrid);
  }

  function renderTimelineTab(wrap) {
    if (!data) return;

    const evidenceSet = new Set((data.evidence || []).map(e => e.id));
    const hasWatch = evidenceSet.has('pocket_watch');
    const hasWallClock = evidenceSet.has('wall_clock');
    const hasSoot = evidenceSet.has('red_soot');
    const hasStaffImpact = evidenceSet.has('staff_impact_testimony');
    const hasTunnelSched = evidenceSet.has('tunnel_schedule');
    const hasGideonAlibi = evidenceSet.has('gideon_blackout_alibi');
    const hasGideonNoEarly = evidenceSet.has('gideon_no_early_alibi');
    const hasStaffNoMsg = evidenceSet.has('staff_no_message');
    const hasBurntC = evidenceSet.has('burnt_folder_c');
    const hasDossierC = evidenceSet.has('dossier_missing_file_c');
    const hasVincentConfession = evidenceSet.has('vincent_blackout_confession');
    const hasVincentCutters = evidenceSet.has('wire_cutters') || evidenceSet.has('cut_copper_wire');
    const hasVincentTicket = evidenceSet.has('vincent_ticket');
    const hasVincentStation = evidenceSet.has('vincent_station_alibi');
    const hasLioraLog = evidenceSet.has('liora_patient_log');
    const hasPatientWitness = evidenceSet.has('liora_patient_witness');

    const container = document.createElement('div');
    container.className = 'timeline-container';

    // 1. Header
    const header = document.createElement('div');
    header.className = 'timeline-tab-header';
    header.innerHTML = `
      <div class="timeline-headline">
        <strong>ลำดับเวลา & การหักล้างคำให้การ</strong>
        <small>วิเคราะห์ความสอดคล้องของที่อยู่และพยานช่วง 20:00–21:30</small>
      </div>
    `;
    container.append(header);

    // 2. Critical Timeframe Banner
    const banner = document.createElement('div');
    banner.className = 'timeline-critical-banner' + (hasWatch ? '' : ' unconfirmed');
    if (hasWatch) {
      banner.innerHTML = `
        <div class="timeline-critical-top">
          <span class="timeline-critical-title">ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:26</span>
          <span class="dossier-stamp stamp-critical">ระบุเวลาแล้ว</span>
        </div>
        <div class="timeline-critical-desc">
          นาฬิกาพกแคสเซียนหยุดที่ 20:25 จากแรงกระแทกในอุโมงค์${hasStaffImpact ? ' (ตรงกับเสียงที่พนักงานได้ยิน)' : ''}${hasSoot ? ' พร้อมเขม่าแดงจากปล่องรถจักร' : ''} เหตุฆาตกรรมเกิดขึ้นก่อนที่ผู้สืบสวนจะขึ้นรถไฟที่ฮัลเบิร์ด
        </div>
      `;
    } else {
      banner.innerHTML = `
        <div class="timeline-critical-top">
          <span class="timeline-critical-title">ช่วงเวลาเกิดเหตุ: ยังไม่ยืนยัน</span>
          <span class="dossier-stamp stamp-pending">รอหลักฐานเวลา</span>
        </div>
        <div class="timeline-critical-desc">
          ยังไม่พบวัตถุที่บันทึกเวลาเกิดเหตุโดยตรง ให้ตรวจค้นสิ่งของในห้องตู้ 4 เพื่อหาร่องรอยนาฬิกาหรือเวลาที่แม่นยำ
        </div>
      `;
    }
    container.append(banner);

    // 3. Chronological Rail (Event Nodes)
    const rail = document.createElement('div');
    rail.className = 'timeline-rail';
    rail.innerHTML = `
      <div class="timeline-event-node">
        <span class="timeline-node-time">20:10–20:35</span>
        <span class="timeline-node-title">สถานีฮัลเบิร์ด (ชานชาลา)</span>
        <div class="timeline-node-sub">${hasVincentStation && hasVincentTicket ? '✓ วินเซนต์อยู่ที่เคาน์เตอร์สถานี มีใบรับรองยืนยัน' : 'วินเซนต์แจ้งว่ารอตรวจตัวตนที่สถานี'}</div>
      </div>
      <div class="timeline-event-node ${hasWatch ? 'critical-node' : ''}">
        <span class="timeline-node-time">20:20–20:26</span>
        <span class="timeline-node-title">รถไฟวิ่งผ่านอุโมงค์ · ห้องตู้ 4</span>
        <div class="timeline-node-sub">${hasWatch ? '⚡ แคสเซียนถูกทำร้าย กลไกนาฬิกาพกหยุดเดิน' : 'คาดว่าเป็นช่วงที่มีเสียงกระแทกในห้องพัก'}</div>
      </div>
      <div class="timeline-event-node">
        <span class="timeline-node-time">20:45</span>
        <span class="timeline-node-title">สถานีฮัลเบิร์ด (ออกขบวน)</span>
        <div class="timeline-node-sub">นรินทร์ เวล ก้าวขึ้นรถไฟ พบกิเดียนที่ตู้เลานจ์</div>
      </div>
      <div class="timeline-event-node ${hasWallClock || hasVincentConfession ? 'active-node' : ''}">
        <span class="timeline-node-time">21:15–21:18</span>
        <span class="timeline-node-title">ไฟบนขบวนดับวูบ</span>
        <div class="timeline-node-sub">${hasWallClock ? 'นาฬิกาไฟฟ้าตู้ 4 หยุดที่ 21:15' : 'สายไฟหลักถูกตัด'}${hasGideonAlibi ? ' · กิเดียนอยู่กับคุณที่เลานจ์' : ''}</div>
      </div>
      <div class="timeline-event-node">
        <span class="timeline-node-time">21:20</span>
        <span class="timeline-node-title">พบศพแคสเซียน รีด</span>
        <div class="timeline-node-sub">พนักงานเปิดประตูห้องตู้ 4 และตาม ดร. ลิโอรา มาตรวจ</div>
      </div>
      <div class="timeline-event-node active-node">
        <span class="timeline-node-time">21:30</span>
        <span class="timeline-node-title">เริ่มการสืบสวน</span>
        <div class="timeline-node-sub">เหลือ 90 นาทีก่อนรถไฟถึงสถานีปลายทางเวสต์มาร์ช</div>
      </div>
    `;
    container.append(rail);

    // 4. Suspect Alibi & Contradiction Cards
    const suspectsGrid = document.createElement('div');
    suspectsGrid.className = 'timeline-suspects-grid';

    // Gideon Card
    const gideonCard = document.createElement('div');
    gideonCard.className = 'timeline-suspect-card';
    let gideonStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
    let gideonFindings = 'กิเดียนอ้างว่าอยู่กับคุณตอนไฟดับ 21:15 กำลังรอหลักฐานยืนยันว่าช่วงเกิดเหตุที่แท้จริงเกิดขึ้นเมื่อใด';
    if (hasWatch) {
      gideonStampHtml = '<span class="dossier-stamp stamp-contradiction">หักล้างแล้ว / CONTRADICTION</span>';
      gideonFindings = 'คำอ้างช่วงไฟดับ (21:15) ไร้ผล! เหตุฆาตกรรมเกิดช่วง 20:20–20:26 ซึ่งกิเดียนยอมรับว่าอยู่คนเดียวและไม่มีพยานยืนยันที่อยู่';
      if (hasStaffNoMsg) {
        gideonFindings += '<br><strong style="color:#e5a440;">[เจตนาลวง / FABRICATION]</strong> พนักงานยืนยันว่าไม่เคยฝากข่าวเลื่อนนัด กิเดียนสร้างเรื่องเท็จเพื่อรั้งตัวคุณไว้ที่เลานจ์';
      }
      if (hasBurntC && hasDossierC) {
        gideonFindings += '<br><strong style="color:#ee6b54;">[พบแรงจูงใจ / MOTIVE]</strong> เศษเอกสารที่เผามีลายเซ็น G.H. เพื่อทำลายความรับผิดในคดีเบลล์เวเธอร์';
      }
    }
    gideonCard.innerHTML = `
      <div class="timeline-card-header">
        <span class="timeline-suspect-name">กิเดียน ฮาร์ต (Gideon Hart)</span>
        ${gideonStampHtml}
      </div>
      <div class="timeline-alibi-claim">“ตอนไฟดับคุณอยู่กับผม คุณยืนยันให้ผมได้”</div>
      <div class="timeline-evidence-findings">
        <span class="timeline-findings-title">ผลการวิเคราะห์พยานหลักฐาน:</span>
        ${gideonFindings}
      </div>
    `;
    suspectsGrid.append(gideonCard);

    // Vincent Card
    const vincentCard = document.createElement('div');
    vincentCard.className = 'timeline-suspect-card';
    let vincentStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
    let vincentFindings = 'วินเซนต์นั่งเงียบอยู่ตู้ 6 มีพิรุธและท่าทางวิตกกังวล';
    if (hasVincentTicket && hasVincentStation) {
      vincentStampHtml = '<span class="dossier-stamp stamp-verified">ยืนยันแล้ว / VERIFIED</span>';
      vincentFindings = 'พ้นข้อหาฆาตกรรม! ตั๋วรถไฟและใบรับรองของนายสถานียืนยันว่าเขาอยู่ที่เคาน์เตอร์สถานีฮัลเบิร์ดช่วง 20:10–20:35 จึงไม่อาจอยู่ในห้องเกิดเหตุช่วง 20:20–20:26 ได้';
      if (hasVincentConfession) {
        vincentFindings += ' (เขายอมรับว่าตัดสายไฟตอน 21:15 เพื่อขโมยกระเป๋าเท่านั้น)';
      }
    } else if (hasVincentConfession || hasVincentCutters) {
      vincentStampHtml = '<span class="dossier-stamp stamp-suspect">ต้องสงสัย / SUSPECTED</span>';
      vincentFindings = 'พบหลักฐานการตัดสายไฟหรือคราบเลือด จำเป็นต้องหาหลักฐานยืนยันที่อยู่ช่วง 20:20–20:26 เพื่อพิสูจน์ความบริสุทธิ์';
    }
    vincentCard.innerHTML = `
      <div class="timeline-card-header">
        <span class="timeline-suspect-name">วินเซนต์ เกรย์ (Vincent Gray)</span>
        ${vincentStampHtml}
      </div>
      <div class="timeline-alibi-claim">“ผมตัดสายไฟตอนสามทุ่มสิบห้า แต่ผมไม่ได้ฆ่าเขา”</div>
      <div class="timeline-evidence-findings">
        <span class="timeline-findings-title">ผลการวิเคราะห์พยานหลักฐาน:</span>
        ${vincentFindings}
      </div>
    `;
    suspectsGrid.append(vincentCard);

    // Liora Card
    const lioraCard = document.createElement('div');
    lioraCard.className = 'timeline-suspect-card';
    let lioraStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
    let lioraFindings = 'ดร. ลิโอรา อ้างว่าดูแลผู้ป่วยที่ตู้ 3 กำลังรอตรวจสมุดบันทึกในห้องแพทย์และสอบถามผู้ป่วย';
    if (hasLioraLog && hasPatientWitness) {
      lioraStampHtml = '<span class="dossier-stamp stamp-verified">ยืนยันแล้ว / VERIFIED</span>';
      lioraFindings = 'พ้นข้อหาฆาตกรรม! สมุดบันทึกการรักษาในห้องแพทย์และคำให้การของผู้ป่วยตู้ 3 สอดคล้องกัน ยืนยันว่าเธออยู่ดูแลคนไข้ตลอดช่วงที่รถไฟวิ่งในอุโมงค์ (20:20–20:26)';
    }
    lioraCard.innerHTML = `
      <div class="timeline-card-header">
        <span class="timeline-suspect-name">ดร. ลิโอรา เวนน์ (Dr. Liora Venn)</span>
        ${lioraStampHtml}
      </div>
      <div class="timeline-alibi-claim">“ฉันอยู่ดูแลผู้ป่วยที่ตู้เสบียงตลอดช่วงรถไฟวิ่งในอุโมงค์”</div>
      <div class="timeline-evidence-findings">
        <span class="timeline-findings-title">ผลการวิเคราะห์พยานหลักฐาน:</span>
        ${lioraFindings}
      </div>
    `;
    suspectsGrid.append(lioraCard);

    container.append(suspectsGrid);
    wrap.append(container);
  }

  // Journal Dispatcher
  function journal() {
    const wrap = $('journalContent');
    if (!wrap) return;
    wrap.replaceChildren();

    if (!data) {
      wrap.append(empty('กำลังเปิดแฟ้มคดี', 'รอสักครู่…'));
      return;
    }

    if (activeTab === 'chat') {
      renderChatTab(wrap);
    } else if (activeTab === 'people') {
      renderPeopleTab(wrap);
    } else if (activeTab === 'timeline') {
      renderTimelineTab(wrap);
    } else {
      // Default: 'evidence' (Items & Documents)
      renderEvidenceTab(wrap);
    }
  }

  // Refresh data from /journal API
  async function refresh() {
    if (!gameState) return;
    drawScene(gameState.current_location);
    map();
    const request = ++revision;

    try {
      const res = await fetch(`${API_BASE}/journal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
        signal: AbortSignal.timeout(8000)
      });
      if (!res.ok) throw Error();
      const next = await res.json();
      if (request !== revision) return;
      data = next;

      for (const item of [...data.evidence, ...data.visible]) {
        objectsMap[item.id] = item.name;
      }

      const evCount = $('evidenceCount');
      if (evCount) evCount.textContent = data.evidence.length;
      const dedCount = $('deductionCount');
      if (dedCount) dedCount.textContent = data.case_closed ? data.deductions.length : '—';

      // Suspect Select in Case Board
      const select = $('suspectSelect');
      if (select && !select.options.length) {
        data.people.filter(p => p.accusable !== false).forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.id;
          opt.textContent = p.name.split(' (')[0];
          select.append(opt);
        });
      }

      // Visible Objects in Center Column (Interactive Clickable Chips)
      const visible = $('visibleObjects');
      if (visible) {
        visible.replaceChildren();
        if (data.visible && data.visible.length) {
          data.visible.forEach(o => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'object-button quick-inspect-btn';
            btn.title = `คลิกเพื่อตรวจ ${o.name}`;
            btn.innerHTML = `<span class="chip-lens">🔍</span> ${o.name}`;
            btn.onclick = () => fillInput(`ตรวจ${o.name}`);
            visible.append(btn);
          });
        } else {
          const emptySpan = document.createElement('span');
          emptySpan.className = 'muted';
          emptySpan.textContent = typeof gameOver !== 'undefined' && gameOver ? 'คดีปิดแล้ว' : 'ไม่มีสิ่งที่ตรวจเพิ่มได้ในตู้นี้';
          visible.append(emptySpan);
        }
      }

      // Update Journal Status text
      const statusEl = $('journalStatus');
      if (statusEl) {
        statusEl.textContent = typeof gameOver !== 'undefined' && gameOver
          ? 'ปิดแฟ้มคดีแล้ว'
          : (data.scene_followups?.length
            ? 'มีบทสนทนาใหม่ในสมุดคดี'
            : (data.inference_questions?.length && !data.validated_claims?.length
              ? 'มีประเด็นให้เสนอข้อสรุป'
              : 'บันทึกพร้อมใช้งาน'));
      }

      board();
      journal();
    } catch {
      if (request === revision) {
        const statusEl = $('journalStatus');
        if (statusEl) {
          statusEl.textContent = 'โหลดสมุดไม่สำเร็จ · คลิกเพื่อลองใหม่';
          statusEl.onclick = refresh;
        }
      }
    }
  }

  function updateChatTab() {
    if (activeTab === 'chat') {
      const wrap = $('journalContent');
      if (wrap) {
        wrap.replaceChildren();
        renderChatTab(wrap);
      }
    }
  }

  function init() {
    drawScene('lounge_car');
    map();
    journal();

    const select = $('suspectSelect');
    if (select) select.onchange = board;

    document.querySelectorAll('[data-tab]').forEach((b, i, all) => {
      b.onclick = () => {
        activeTab = b.dataset.tab;
        all.forEach(x => x.setAttribute('aria-selected', String(x === b)));
        const jc = $('journalContent');
        if (jc) jc.setAttribute('aria-labelledby', b.id);
        journal();
      };
      b.onkeydown = e => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
          e.preventDefault();
          const next = all[(i + (e.key === 'ArrowRight' ? 1 : all.length - 1)) % all.length];
          next.click();
          next.focus();
        }
      };
    });
  }

  document.addEventListener('DOMContentLoaded', init);

  return { refresh, updateChatTab, openDocument };
})();
