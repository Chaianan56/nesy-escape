/**
 * frontend/pixel.js — แดชบอร์ดสืบสวนและสมุดบันทึกคดีแบบโต้ตอบ (PixelUI)
 * 
 * หน้าที่:
 * 1. แสดงผลแผนผังขบวนรถไฟ 6 ตู้ (Train Route HUD)
 * 2. จัดการสมุดคดี (Detective Journal): แท็บหลักฐาน, บัญชีพยาน, เอกสารสำคัญ, ประเด็นสงสัย
 * 3. แสดงผลตัวอ่านเอกสารในเกม (In-game Document Reader)
 * 4. แสดงผลเรดาร์ชาร์ตและสถิติโปรไฟล์พฤติกรรมผู้เล่น (Profiler Details & Radar Chart)
 */
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

    const displayLabels = ['หัวรถจักร', 'ระบบไฟฟ้า', 'ตู้เสบียง', 'ชั้นหนึ่ง', 'ตู้เลานจ์', 'ชั้นสอง'];

    const renderPin = cx => `
      <g class="train-active-pin" transform="translate(${cx} 16)" filter="url(#trainGoldGlow)">
        <path d="M 0 0 C -4 -5.5 -6.5 -8.5 -6.5 -12.5 A 6.5 6.5 0 0 1 6.5 -12.5 C 6.5 -8.5 4 -5.5 0 0 Z" fill="#ffd580" stroke="#fff4d4" stroke-width="0.8"/>
        <circle cx="0" cy="-12.5" r="2.4" fill="#070c12"/>
      </g>`;

    const renderActivePip = cx => `
      <path d="M ${cx - 12} 75 H ${cx - 4} M ${cx + 4} 75 H ${cx + 12}" stroke="#ffd580" stroke-width="0.8"/>
      <circle cx="${cx}" cy="75" r="1.5" fill="#ffd580"/>`;

    const passengerCar = (x, index) => {
      const [id, label] = rooms[index];
      const active = currentLocation === id;
      const stroke = active ? '#ffd580' : '#7e6742';
      const subStroke = active ? '#e8be6e' : '#58472d';
      const winBg = active ? 'url(#warmLitWindow)' : 'url(#dimWindow)';
      const winBorder = active ? '#fff0c2' : '#57462c';
      const sil = active ? '#1a1309' : '#141009';
      const cx = x + 56;

      let windowsHtml = '';
      if (index === 1) {
        // Luggage / Electrical
        windowsHtml = `
          <rect x="${x + 16}" y="32" width="16" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <line x1="${x + 24}" y1="32" x2="${x + 24}" y2="45" stroke="${winBorder}" stroke-width="0.6"/>
          <rect x="${x + 40}" y="31" width="32" height="24" fill="#131920" stroke="${subStroke}" stroke-width="0.8"/>
          <line x1="${x + 56}" y1="31" x2="${x + 56}" y2="55" stroke="${subStroke}" stroke-width="1"/>
          <line x1="${x + 48}" y1="34" x2="${x + 48}" y2="52" stroke="${subStroke}" stroke-width="0.5"/>
          <line x1="${x + 64}" y1="34" x2="${x + 64}" y2="52" stroke="${subStroke}" stroke-width="0.5"/>
          <rect x="${x + 80}" y="32" width="16" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <line x1="${x + 88}" y1="32" x2="${x + 88}" y2="45" stroke="${winBorder}" stroke-width="0.6"/>
        `;
      } else if (index === 2) {
        // Dining car with dining tables, lamps, and diner silhouettes
        windowsHtml = `
          <rect x="${x + 14}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <path d="M${x + 23} 45 v-4 h4 v4 M${x + 24} 41 l-2 -3 h4 l-2 3" stroke="${sil}" fill="${sil}" stroke-width="0.5"/>
          <circle cx="${x + 19}" cy="38" r="2.2" fill="${sil}"/>
          <circle cx="${x + 31}" cy="38" r="2.2" fill="${sil}"/>

          <rect x="${x + 45}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <path d="M${x + 54} 45 v-4 h4 v4 M${x + 55} 41 l-2 -3 h4 l-2 3" stroke="${sil}" fill="${sil}" stroke-width="0.5"/>
          <circle cx="${x + 50}" cy="37" r="2.4" fill="${sil}"/>
          <circle cx="${x + 62}" cy="37" r="2.4" fill="${sil}"/>

          <rect x="${x + 76}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <path d="M${x + 85} 45 v-4 h4 v4" stroke="${sil}" fill="${sil}" stroke-width="0.5"/>
          <circle cx="${x + 81}" cy="38" r="2.2" fill="${sil}"/>
          <circle cx="${x + 93}" cy="38" r="2.2" fill="${sil}"/>
        `;
      } else if (index === 3) {
        // First Class with draped curtains and luxury passenger silhouettes
        windowsHtml = `
          <rect x="${x + 14}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <path d="M${x + 15} 33 q3 5 1 11 h-1 v-11 M${x + 35} 33 q-3 5 -1 11 h1 v-11" fill="${subStroke}" stroke="none"/>
          <circle cx="${x + 25}" cy="38" r="2.5" fill="${sil}"/>

          <rect x="${x + 45}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <path d="M${x + 46} 33 q3 5 1 11 h-1 v-11 M${x + 66} 33 q-3 5 -1 11 h1 v-11" fill="${subStroke}" stroke="none"/>
          <circle cx="${x + 56}" cy="37" r="2.5" fill="${sil}"/>

          <rect x="${x + 76}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <path d="M${x + 77} 33 q3 5 1 11 h-1 v-11 M${x + 97} 33 q-3 5 -1 11 h1 v-11" fill="${subStroke}" stroke="none"/>
          <circle cx="${x + 87}" cy="38" r="2.5" fill="${sil}"/>
        `;
      } else if (index === 4) {
        // Lounge Bar with bar stools and relaxed patron silhouettes
        windowsHtml = `
          <rect x="${x + 14}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <circle cx="${x + 22}" cy="38" r="2.2" fill="${sil}"/>
          <rect x="${x + 29}" y="40" width="5" height="5" fill="${sil}"/>

          <rect x="${x + 45}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <circle cx="${x + 52}" cy="37" r="2.4" fill="${sil}"/>
          <circle cx="${x + 60}" cy="37" r="2.4" fill="${sil}"/>
          <line x1="${x + 56}" y1="41" x2="${x + 56}" y2="45" stroke="${sil}" stroke-width="1"/>

          <rect x="${x + 76}" y="32" width="22" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <circle cx="${x + 85}" cy="38" r="2.2" fill="${sil}"/>
        `;
      } else {
        // Second Class standard coach
        windowsHtml = `
          <rect x="${x + 12}" y="32" width="18" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <circle cx="${x + 21}" cy="38" r="2.1" fill="${sil}"/>
          <rect x="${x + 35}" y="32" width="18" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <circle cx="${x + 44}" cy="38" r="2.1" fill="${sil}"/>
          <rect x="${x + 58}" y="32" width="18" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <circle cx="${x + 67}" cy="38" r="2.1" fill="${sil}"/>
          <rect x="${x + 81}" y="32" width="18" height="13" rx="1.5" fill="${winBg}" stroke="${winBorder}" stroke-width="0.8"/>
          <circle cx="${x + 90}" cy="38" r="2.1" fill="${sil}"/>
        `;
      }

      return `
        <g class="train-svg-car${active ? ' active' : ''}" data-room-index="${index}" style="cursor: pointer;">
          ${active ? renderPin(cx) : ''}
          ${active ? `<rect class="train-active-glow" x="${x + 2}" y="20" width="108" height="40" rx="3" fill="none" stroke="#ffd580" stroke-width="1.8" filter="url(#trainGoldGlow)"/>` : ''}

          <!-- Clerestory Roof -->
          <path d="M${x + 18} 25 h76 v-3 h-76 z" fill="#18130c" stroke="${stroke}" stroke-width="1"/>
          <line x1="${x + 32}" y1="23.5" x2="${x + 36}" y2="23.5" stroke="${subStroke}" stroke-width="0.6"/>
          <line x1="${x + 48}" y1="23.5" x2="${x + 52}" y2="23.5" stroke="${subStroke}" stroke-width="0.6"/>
          <line x1="${x + 64}" y1="23.5" x2="${x + 68}" y2="23.5" stroke="${subStroke}" stroke-width="0.6"/>
          <line x1="${x + 80}" y1="23.5" x2="${x + 84}" y2="23.5" stroke="${subStroke}" stroke-width="0.6"/>

          <!-- Main Curved Roof -->
          <path d="M${x + 4} 29 c8 -4 14 -4 14 -4 h76 c0 0 6 0 14 4 z" fill="#201a12" stroke="${stroke}" stroke-width="1"/>

          <!-- Carriage Body Shell -->
          <rect x="${x + 4}" y="29" width="104" height="27" rx="1.5" fill="#101720" stroke="${stroke}" stroke-width="1.2"/>
          <line x1="${x + 4}" y1="46" x2="${x + 108}" y2="46" stroke="${subStroke}" stroke-width="0.8"/>
          <rect x="${x + 6}" y="56" width="100" height="3" fill="#1b150f" stroke="${subStroke}" stroke-width="0.8"/>

          <!-- Windows and Interior Art -->
          ${windowsHtml}

          <!-- Bogie 1 (Front Wheels) -->
          <path d="M${x + 15} 63 h29 m-23 2 h17" stroke="${subStroke}" stroke-width="1.2"/>
          <circle cx="${x + 22}" cy="65" r="5" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="${x + 22}" cy="65" r="1.5" fill="${active ? '#ffd580' : '#453822'}"/>
          <circle cx="${x + 38}" cy="65" r="5" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="${x + 38}" cy="65" r="1.5" fill="${active ? '#ffd580' : '#453822'}"/>

          <!-- Bogie 2 (Rear Wheels) -->
          <path d="M${x + 67} 63 h29 m-23 2 h17" stroke="${subStroke}" stroke-width="1.2"/>
          <circle cx="${x + 74}" cy="65" r="5" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="${x + 74}" cy="65" r="1.5" fill="${active ? '#ffd580' : '#453822'}"/>
          <circle cx="${x + 90}" cy="65" r="5" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="${x + 90}" cy="65" r="1.5" fill="${active ? '#ffd580' : '#453822'}"/>

          <!-- Coupler to next car -->
          <line x1="${x + 108}" y1="50" x2="${x + 116}" y2="50" stroke="${subStroke}" stroke-width="1.8"/>

          <!-- Under-label & pip -->
          ${active ? renderActivePip(cx) : ''}
          <text x="${cx}" y="89" text-anchor="middle" class="train-car-label${active ? ' active' : ''}" fill="${active ? '#ffd580' : '#b3ada0'}" font-size="${active ? '13.5' : '12.5'}" font-weight="${active ? 'bold' : '600'}" font-family="'Segoe UI', Tahoma, sans-serif">${displayLabels[index]}</text>

          <!-- Interaction Hit Area -->
          <rect x="${x}" y="12" width="112" height="76" fill="transparent" aria-hidden="true"/>
        </g>
      `;
    };

    // Locomotive Car (Index 0)
    const renderLocomotive = () => {
      const active = currentLocation === rooms[0][0];
      const stroke = active ? '#ffd580' : '#7e6742';
      const subStroke = active ? '#e8be6e' : '#58472d';
      const cx = 67;

      return `
        <g class="train-svg-car${active ? ' active' : ''}" data-room-index="0" style="cursor: pointer;">
          ${active ? renderPin(cx) : ''}
          ${active ? `<rect class="train-active-glow" x="6" y="20" width="122" height="40" rx="3" fill="none" stroke="#ffd580" stroke-width="1.8" filter="url(#trainGoldGlow)"/>` : ''}

          <!-- Cowcatcher / Pilot -->
          <polygon points="14,70 4,70 16,57" fill="#18130c" stroke="${stroke}" stroke-width="1"/>
          <line x1="7" y1="67" x2="15" y2="67" stroke="${subStroke}" stroke-width="0.8"/>
          <line x1="10" y1="63" x2="16" y2="63" stroke="${subStroke}" stroke-width="0.8"/>

          <!-- Front Pilot Wheel -->
          <circle cx="21" cy="65" r="4.5" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="21" cy="65" r="1.5" fill="${active ? '#ffd580' : '#453822'}"/>

          <!-- 3 Driver Wheels & Rod -->
          <circle cx="36" cy="62" r="8" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="36" cy="62" r="2.5" fill="${active ? '#ffd580' : '#453822'}"/>
          <circle cx="56" cy="62" r="8" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="56" cy="62" r="2.5" fill="${active ? '#ffd580' : '#453822'}"/>
          <circle cx="76" cy="62" r="8" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="76" cy="62" r="2.5" fill="${active ? '#ffd580' : '#453822'}"/>
          <rect x="36" y="60.5" width="40" height="3" rx="1.5" fill="${active ? '#ffd580' : '#8e7548'}"/>

          <!-- Boiler & Bands -->
          <rect x="22" y="31" width="60" height="22" fill="#161c22" stroke="${stroke}" stroke-width="1"/>
          <line x1="37" y1="31" x2="37" y2="53" stroke="${subStroke}" stroke-width="0.8"/>
          <line x1="52" y1="31" x2="52" y2="53" stroke="${subStroke}" stroke-width="0.8"/>
          <line x1="67" y1="31" x2="67" y2="53" stroke="${subStroke}" stroke-width="0.8"/>

          <!-- Headlamp -->
          <path d="M14 41 h8 v-6 h-8 z" fill="#2a2215" stroke="${stroke}" stroke-width="0.8"/>
          <circle cx="14" cy="38" r="3" fill="#ffe082" filter="url(#trainGoldGlow)"/>

          <!-- Smokestack & Domes -->
          <path d="M28 31 v-8 h7 v8 z" fill="#1a140d" stroke="${stroke}" stroke-width="1"/>
          <path d="M26 23 h11 l-2 3 h-7 z" fill="${stroke}"/>
          <path d="M44 31 c0 -5 7 -5 7 0 z" fill="#1a140d" stroke="${stroke}" stroke-width="1"/>
          <path d="M64 31 c0 -4 6 -4 6 0 z" fill="#1a140d" stroke="${stroke}" stroke-width="1"/>

          <!-- Cab -->
          <path d="M82 53 h22 v-29 h-22 z" fill="#181e26" stroke="${stroke}" stroke-width="1"/>
          <path d="M79 24 h27" stroke="${stroke}" stroke-width="1.5"/>
          <path d="M87 34 v8 h12 v-8 c0 -3 -12 -3 -12 0 z" fill="${active ? 'url(#warmLitWindow)' : 'url(#dimWindow)'}" stroke="${active ? '#ffd580' : '#57482f'}" stroke-width="0.8"/>

          <!-- Tender with coal -->
          <path d="M106 53 h20 v-16 h-20 z" fill="#181e26" stroke="${stroke}" stroke-width="1"/>
          <path d="M107 37 q10 -5 18 0 z" fill="#0b0e12" stroke="#332a1d"/>
          <circle cx="112" cy="65" r="4.5" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="112" cy="65" r="1.5" fill="${active ? '#ffd580' : '#453822'}"/>
          <circle cx="122" cy="65" r="4.5" fill="#14181d" stroke="${stroke}" stroke-width="1"/>
          <circle cx="122" cy="65" r="1.5" fill="${active ? '#ffd580' : '#453822'}"/>

          <!-- Coupler to Car 1 -->
          <line x1="126" y1="50" x2="134" y2="50" stroke="${subStroke}" stroke-width="1.8"/>

          <!-- Under-label & pip -->
          ${active ? renderActivePip(cx) : ''}
          <text x="${cx}" y="89" text-anchor="middle" class="train-car-label${active ? ' active' : ''}" fill="${active ? '#ffd580' : '#b3ada0'}" font-size="${active ? '13.5' : '12.5'}" font-weight="${active ? 'bold' : '600'}" font-family="'Segoe UI', Tahoma, sans-serif">${displayLabels[0]}</text>

          <!-- Interaction Hit Area -->
          <rect x="4" y="12" width="126" height="76" fill="transparent" aria-hidden="true"/>
        </g>
      `;
    };

    // Sleepers (track ties) generator across the train
    let sleepersHtml = '';
    for (let t = 10; t <= 740; t += 12) {
      sleepersHtml += `<line x1="${t}" y1="70" x2="${t}" y2="74" stroke="#4a3c27" stroke-width="1"/>`;
    }

    const svg = `
      <svg class="train-map-svg" viewBox="0 0 748 98" role="group" aria-label="แผนผังตู้รถไฟ เลือกตู้เพื่อเดินทาง">
        <defs>
          <filter id="trainGoldGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2.2" result="blur"/>
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
          <linearGradient id="warmLitWindow" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#fff2cc"/>
            <stop offset="100%" stop-color="#e5af4b"/>
          </linearGradient>
          <linearGradient id="dimWindow" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#2a2014"/>
            <stop offset="100%" stop-color="#151009"/>
          </linearGradient>
        </defs>

        <!-- Rails & Sleepers -->
        ${sleepersHtml}
        <line x1="6" y1="71" x2="742" y2="71" stroke="#685536" stroke-width="1.2"/>
        <line x1="6" y1="73" x2="742" y2="73" stroke="#4f3f27" stroke-width="1.2"/>

        <!-- Train Cars: Locomotive + 5 Passenger Cars -->
        ${renderLocomotive()}
        ${passengerCar(134, 1)}
        ${passengerCar(246, 2)}
        ${passengerCar(358, 3)}
        ${passengerCar(470, 4)}
        ${passengerCar(582, 5)}
      </svg>
    `;

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
      car.setAttribute('aria-label', `${index === 0 ? 'หัวรถจักร พื้นที่หวงห้าม' : `ตู้ ${label}`} · ${rooms[index][2]}${current ? ' · ตำแหน่งปัจจุบัน' : ''}`);
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
  }

  // Case Board
  function board() {
    const wrap = $('pillarBoard');
    if (!wrap) return;
    wrap.replaceChildren();
    if (!data) return;

    const select = $('suspectSelect');
    const selectedSuspect = select ? select.value : Object.keys(data.pillars || {})[0];
    const person = (data.people || []).find(p => p.id === selectedSuspect);

    if (!data.case_closed) {
      const box = document.createElement('div');
      box.className = 'suspect-board-preview';

      if (person) {
        const isPersonEncountered = Boolean(
          person.encountered !== undefined
            ? person.encountered
            : (person.discovered !== undefined
              ? person.discovered
              : (person.here || (gameState?.visited_locations && gameState.visited_locations.includes(person.location)) || person.interrogated))
        );
        const metaRow = document.createElement('div');
        metaRow.className = 'suspect-board-meta';
        const locSpan = document.createElement('span');
        const locLabel = isPersonEncountered
          ? ((locationsMap && locationsMap[person.location]) || person.location || 'บนขบวนรถไฟ')
          : 'ยังไม่พบตัว (ต้องสำรวจ)';
        locSpan.textContent = `📍 ตำแหน่ง: ${locLabel}`;
        const statusSpan = document.createElement('span');
        statusSpan.className = isPersonEncountered && person.interrogated ? 'badge allowed' : 'badge';
        statusSpan.textContent = isPersonEncountered
          ? (person.interrogated ? '✓ สอบปากคำแล้ว' : 'ยังไม่ได้สอบปากคำ')
          : 'รอการพบตัว';
        metaRow.append(locSpan, statusSpan);
        box.append(metaRow);
      }

      const pillarsList = document.createElement('div');
      pillarsList.className = 'suspect-board-pillars';
      Object.entries(data.pillar_labels || {}).forEach(([id, label]) => {
        const row = document.createElement('div');
        row.className = 'pillar-row';
        const line = document.createElement('div');
        const l = document.createElement('span');
        l.textContent = label;
        const r = document.createElement('span');
        r.className = 'pillar-missing';
        r.textContent = 'รอตรวจสอบเมื่อกล่าวหา';
        line.append(l, r);
        const p = document.createElement('progress');
        p.max = 1;
        p.value = 0;
        p.className = 'pillar-progress-pending';
        row.append(line, p);
        pillarsList.append(row);
      });
      box.append(pillarsList);

      const note = document.createElement('div');
      note.className = 'pillar-board-note';
      const count = data.evidence ? data.evidence.length : 0;
      note.innerHTML = '<small>✦ <b>กระดานสี่เสา</b>จะถูกประเมินเมื่อคุณพิมพ์ <code>กล่าวหา [ชื่อคน]</code> หรือเมื่อปิดสำนวนคดี (ระบบไม่เฉลยคำตอบล่วงหน้าระหว่างสืบสวน เพื่อให้คุณเชื่อมโยงหลักฐานเอง)<br>✦ ดูรายละเอียดหลักฐานทั้ง ' + count + ' ชิ้นที่พบได้ที่แท็บ <b>หลักฐาน</b> บนแถบขวาของหน้าจอหลัก</small>';
      box.append(note);

      wrap.append(box);
      return;
    }
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
    const messages = Array.from(feed?.children || []).filter(node => !node.classList.contains('msg-loading'));
    if (!messages.length) {
      wrap.append(empty('ยังไม่มีประวัติการคุย', 'พิมพ์คำสั่งสืบสวนหรือกดสำรวจตรงหน้า บันทึกการสนทนาจะปรากฏที่นี่'));
      return;
    }

    const header = document.createElement('div');
    header.className = 'archive-tab-header';
    header.innerHTML = `
      <div class="archive-headline">
        <strong>บันทึกบทสนทนาและคำสั่ง</strong>
        <small>${messages.length} ข้อความ</small>
      </div>
      <button type="button" class="chip-btn scroll-latest-btn" id="scrollTabLatest">ไปล่าสุด ↓</button>
    `;
    wrap.append(header);

    const logContainer = document.createElement('div');
    logContainer.className = 'archive-chat-log';

    messages.forEach((node, idx) => {
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
      wrap.scrollTo({ top: wrap.scrollHeight, behavior: 'smooth' });
    });
    wrap.scrollTop = wrap.scrollHeight;
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
          chip.classList.add('has-image');
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

    const encounteredCount = data.people.filter(p => Boolean(
      p.encountered !== undefined
        ? p.encountered
        : (p.discovered !== undefined
          ? p.discovered
          : (p.here || (gameState?.visited_locations && gameState.visited_locations.includes(p.location)) || p.interrogated))
    )).length;

    const header = document.createElement('div');
    header.className = 'archive-tab-header';
    header.innerHTML = `
      <div class="archive-headline">
        <strong>บุคคลบนขบวนรถไฟ</strong>
        <small>พบแล้ว ${encounteredCount} / ${data.people.length} คน</small>
      </div>
    `;
    wrap.append(header);

    const peopleGrid = document.createElement('div');
    peopleGrid.className = 'people-grid';
    data.people.forEach(p => {
      const card = document.createElement('div');
      const isEncountered = Boolean(
        p.encountered !== undefined
          ? p.encountered
          : (p.discovered !== undefined
            ? p.discovered
            : (p.here || (gameState?.visited_locations && gameState.visited_locations.includes(p.location)) || p.interrogated))
      );

      if (!isEncountered) {
        card.className = 'person-card person-unknown';
        const image = document.createElement('div');
        image.className = 'archive-image-slot archive-image-slot-person archive-image-slot-unknown';
        image.setAttribute('role', 'img');
        image.setAttribute('aria-label', 'บุคคลที่ยังไม่พบตัว');
        const mark = document.createElement('span');
        mark.setAttribute('aria-hidden', 'true');
        mark.className = 'silhouette-icon';
        mark.textContent = '👤';
        const caption = document.createElement('small');
        caption.textContent = 'ยังไม่พบตัว';
        image.append(mark, caption);
        card.append(image);

        const top = document.createElement('div');
        top.className = 'person-top';
        const name = document.createElement('strong');
        name.className = 'person-name person-name-unknown';
        name.textContent = '??? (ยังไม่พบตัว)';

        const badge = document.createElement('span');
        badge.className = 'person-badge badge-unknown';
        badge.textContent = '❓ ยังไม่พบตัว';

        top.append(name, badge);
        card.append(top);

        const hint = document.createElement('small');
        hint.className = 'person-card-hint';
        hint.textContent = 'เดินทางไปตู้ต่าง ๆ บนขบวนรถไฟเพื่อตามหาบุคคลนี้';
        card.append(hint);

        makeCardClickable(card, () => {
          showArchiveDetail({
            kind: 'person',
            id: 'unknown',
            title: '??? (ยังไม่พบตัว)',
            subtitle: 'บนขบวนรถไฟ',
            sections: [{
              title: 'สถานะการสืบสวน',
              text: 'คุณยังไม่เคยพบเจอบุคคลนี้บนขบวนรถไฟ เดินทางไปยังตู้ต่าง ๆ เพื่อสำรวจและตามหาบุคคล'
            }],
          });
        }, 'บุคคลที่ยังไม่พบตัว');

        peopleGrid.append(card);
        return;
      }

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

    const caseId = data.case_id || 'case_01_gideon';
    const evidenceSet = new Set((data.evidence || []).map(e => e.id));
    const deductionSet = new Set((data.deductions || []).map(d => typeof d === 'string' ? d : d.id));

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
    const hasVincentBlood = evidenceSet.has('vincent_blood');
    const hasMaraJob = evidenceSet.has('mara_job_note');
    const hasLioraLog = evidenceSet.has('liora_patient_log');
    const hasPatientWitness = evidenceSet.has('liora_patient_witness');
    const hasTeaTrace = evidenceSet.has('tea_lozenge_trace');
    const hasLioraEstimate = evidenceSet.has('liora_time_estimate');

    // สรุปตรรกะคดีตามหลักฐานและข้อสรุปที่ค้นพบจริง
    const hasCase01MurderWindow = (hasWatch && (hasSoot || hasStaffImpact || hasTunnelSched)) || deductionSet.has('D01_TRUE_MURDER_WINDOW');
    const hasCase01VincentCleared = (hasVincentStation && hasVincentTicket) || deductionSet.has('D08_VINCENT_CLEARED');
    const hasCase01LioraCleared = (hasLioraLog && hasPatientWitness) || deductionSet.has('D09_LIORA_CLEARED');
    const hasCase01GideonContradicted = (hasWatch || deductionSet.has('D02_BLACKOUT_ALIBI_IRRELEVANT')) && hasGideonAlibi;

    const hasCase02MurderWindow = (hasWallClock && (hasLioraEstimate || hasVincentBlood)) || deductionSet.has('D01_BLACKOUT_MURDER_WINDOW');
    const hasCase02VincentSabotage = (hasVincentCutters && evidenceSet.has('cut_copper_wire')) || deductionSet.has('D02_VINCENT_SABOTAGE');
    const hasCase02VincentContradicted = (hasVincentBlood && (evidenceSet.has('letter_opener') || hasVincentCutters)) || deductionSet.has('D04_VINCENT_BLOOD_SPATTER');
    const hasCase02GideonVerified = hasGideonAlibi && (hasCase02MurderWindow || deductionSet.has('D05_GIDEON_ALIBI_SOLID'));
    const hasCase02LioraCleared = hasPatientWitness || deductionSet.has('D06_LIORA_CLEARED');

    const hasCase03MurderWindow = (hasWatch && (hasLioraEstimate || evidenceSet.has('second_teacup'))) || deductionSet.has('D01_POISON_DEATH_WINDOW');
    const hasCase03PoisonTrace = (hasTeaTrace && hasLioraLog) || deductionSet.has('D03_LIORA_POISON_TRACE');
    const hasCase03LioraAlibiBroken = (hasPatientWitness && hasTunnelSched) || deductionSet.has('D04_LIORA_ALIBI_BROKEN');
    const hasCase03VincentCleared = (hasVincentTicket && (hasCase03MurderWindow || hasCase03PoisonTrace)) || deductionSet.has('D05_VINCENT_CLEARED');
    const hasCase03GideonCleared = (hasGideonAlibi && (hasCase03MurderWindow || hasCase03PoisonTrace)) || deductionSet.has('D06_GIDEON_CLEARED');
    const hasCase03LioraContradicted = hasCase03PoisonTrace || hasCase03LioraAlibiBroken;

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
    let isTimeConfirmed = false;
    let bannerTitle = 'ช่วงเวลาเกิดเหตุ: ยังไม่ยืนยัน';
    let bannerDesc = 'ยังไม่พบวัตถุหรือบันทึกเวลาเกิดเหตุโดยตรง ให้ตรวจค้นสิ่งของในห้องตู้ 4 เพื่อหาร่องรอยนาฬิกาหรือเวลาที่แม่นยำ';

    if (caseId === 'case_02_vincent') {
      isTimeConfirmed = hasCase02MurderWindow;
      if (isTimeConfirmed) {
        bannerTitle = 'ช่วงเวลาเกิดเหตุรุนแรง: 21:15 – 21:18 (ช่วงไฟดับ)';
        bannerDesc = 'นาฬิกาไฟฟ้าบนผนังห้องตู้ 4 หยุดที่ 21:15 เลือดสดเพิ่งเริ่มแข็งตัวพร้อมรอยแผลต่อสู้ ยืนยันว่าแคสเซียนถูกแทงเสียชีวิตระหว่างไฟดับ';
      } else if (hasWallClock) {
        bannerTitle = 'ช่วงเวลาเกิดเหตุ: คาดว่าเป็นช่วงไฟดับ (รอผลชันสูตร)';
        bannerDesc = 'นาฬิกาไฟฟ้าบนผนังห้องตู้ 4 หยุดเดินที่ 21:15 รอผลการตรวจสภาพศพหรือเวลาตายเพื่อยืนยันช่วงเวลาเกิดเหตุ';
      }
    } else if (caseId === 'case_03_liora') {
      isTimeConfirmed = hasCase03MurderWindow;
      if (isTimeConfirmed) {
        bannerTitle = 'ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:25 (วางยาพิษอำพราง)';
        bannerDesc = 'นาฬิกาพกหยุดที่ 20:25 เมื่อพิษออกฤทธิ์เฉียบพลัน ริมฝีปากเขียวคล้ำ รูม่านตาขยาย แผลมีดแทงไม่มีการตกเลือดในเนื้อเยื่อ (แผลอำพรางหลังเสียชีวิต!)';
      } else if (hasWatch) {
        bannerTitle = 'ช่วงเวลาเกิดเหตุ: เข็มนาฬิกาหยุด 20:25 (รอตรวจสารพิษ)';
        bannerDesc = 'นาฬิกาพกหยุดเดินที่ 20:25 ในอุโมงค์ รอผลตรวจสภาพศพและสารพิษเพื่อยืนยันสาเหตุและช่วงเวลาเสียชีวิตที่แท้จริง';
      }
    } else {
      isTimeConfirmed = hasWatch || deductionSet.has('D01_TRUE_MURDER_WINDOW');
      if (isTimeConfirmed) {
        bannerTitle = 'ช่วงเวลาเกิดเหตุรุนแรง: 20:20 – 20:26';
        bannerDesc = `นาฬิกาพกแคสเซียนหยุดที่ 20:25 จากแรงกระแทกในอุโมงค์${hasStaffImpact ? ' (ตรงกับเสียงที่พนักงานได้ยิน)' : ''}${hasSoot ? ' พร้อมเขม่าแดงจากปล่องรถจักร' : ''} เหตุฆาตกรรมเกิดขึ้นก่อนที่ผู้สืบสวนจะขึ้นรถไฟที่ฮัลเบิร์ด`;
      }
    }

    banner.className = 'timeline-critical-banner' + (isTimeConfirmed ? '' : ' unconfirmed');
    banner.innerHTML = `
      <div class="timeline-critical-top">
        <span class="timeline-critical-title">${bannerTitle}</span>
        <span class="dossier-stamp ${isTimeConfirmed ? 'stamp-critical' : 'stamp-pending'}">${isTimeConfirmed ? 'ระบุเวลาแล้ว' : 'รอหลักฐานเวลา'}</span>
      </div>
      <div class="timeline-critical-desc">
        ${bannerDesc}
      </div>
    `;
    container.append(banner);

    // 3. Chronological Rail (Event Nodes)
    const rail = document.createElement('div');
    rail.className = 'timeline-rail';

    if (caseId === 'case_02_vincent') {
      rail.innerHTML = `
        <div class="timeline-event-node">
          <span class="timeline-node-time">20:15–20:30</span>
          <span class="timeline-node-title">รถไฟวิ่งในอุโมงค์ · ห้องตู้ 4</span>
          <div class="timeline-node-sub">${hasGideonAlibi ? 'แคสเซียนยังมีชีวิต กิเดียนมาพบเรื่องคดีก่อนเดินกลับตู้เลานจ์' : 'มีรายงานการพบปะพูดคุยในตู้โดยสาร (รอตรวจสอบ)'}</div>
        </div>
        <div class="timeline-event-node">
          <span class="timeline-node-time">20:45</span>
          <span class="timeline-node-title">สถานีฮัลเบิร์ด (ออกขบวน)</span>
          <div class="timeline-node-sub">${hasVincentTicket ? 'วินเซนต์ขึ้นรถไฟที่ตู้ 6 (มีตั๋วระบุสถานีฮัลเบิร์ด) · นรินทร์ เวล ขึ้นรถไฟพบกิเดียนที่เลานจ์' : 'สถานีฮัลเบิร์ด (ออกขบวน) · นรินทร์ เวล ขึ้นรถไฟพบกิเดียนที่เลานจ์'}</div>
        </div>
        <div class="timeline-event-node">
          <span class="timeline-node-time">21:05–21:14</span>
          <span class="timeline-node-title">ตู้สัมภาระ (ระบบไฟ)</span>
          <div class="timeline-node-sub">${hasCase02VincentSabotage ? '✓ พบรอยคีมตัดสายไฟหลักในตู้สัมภาระ' : 'ระบบไฟฟ้าในตู้สัมภาระ (รอตรวจสอบสาเหตุความขัดข้อง)'}</div>
        </div>
        <div class="timeline-event-node ${hasCase02MurderWindow ? 'critical-node' : ''}">
          <span class="timeline-node-time">21:15–21:18</span>
          <span class="timeline-node-title">ไฟบนขบวนดับวูบ · ห้องตู้ 4</span>
          <div class="timeline-node-sub">${hasCase02MurderWindow ? '⚡ 21:16 แคสเซียนถูกแทงเสียชีวิตในความมืด' : 'ไฟฟ้าดับ 3 นาที เกิดเหตุรุนแรงในห้องพัก (ยังไม่ยืนยันช่วงเวลาตาย)'}</div>
        </div>
        <div class="timeline-event-node">
          <span class="timeline-node-time">21:20</span>
          <span class="timeline-node-title">ไฟติด · พบศพแคสเซียน รีด</span>
          <div class="timeline-node-sub">${hasCase02MurderWindow ? 'ไฟติด · พบศพแคสเซียน รีด (ศพยังอุ่น เลือดเพิ่งแข็งตัว)' : 'ไฟติด · พบศพแคสเซียน รีด ในห้องพักตู้ 4'}</div>
        </div>
        <div class="timeline-event-node active-node">
          <span class="timeline-node-time">21:30</span>
          <span class="timeline-node-title">เริ่มการสืบสวน</span>
          <div class="timeline-node-sub">เหลือ 90 นาทีก่อนรถไฟถึงสถานีปลายทางเวสต์มาร์ช</div>
        </div>
      `;
    } else if (caseId === 'case_03_liora') {
      rail.innerHTML = `
        <div class="timeline-event-node">
          <span class="timeline-node-time">20:00–20:10</span>
          <span class="timeline-node-title">ห้องตู้ 4 (ก่อนเข้าอุโมงค์)</span>
          <div class="timeline-node-sub">${hasCase03PoisonTrace ? '✓ เสิร์ฟชาร้อนผสมสารพิษอัลคาลอยด์ให้แคสเซียน' : (hasTeaTrace ? 'พบร่องรอยคราบชาปริศนาในห้องตู้ 4 (รอตรวจสอบ)' : 'ห้องตู้ 4 (ก่อนเข้าอุโมงค์) · มีการนำเครื่องดื่มไปให้ผู้ตาย (รอตรวจสอบ)')}</div>
        </div>
        <div class="timeline-event-node ${hasCase03MurderWindow ? 'critical-node' : ''}">
          <span class="timeline-node-time">20:20–20:25</span>
          <span class="timeline-node-title">รถไฟวิ่งผ่านอุโมงค์ · ห้องตู้ 4</span>
          <div class="timeline-node-sub">${hasCase03MurderWindow ? '⚡ ยาพิษออกฤทธิ์ กลไกนาฬิกาพกหยุดที่ 20:25 · มีร่องรอยการอำพรางบาดแผล' : 'รถไฟวิ่งผ่านอุโมงค์ · ห้องตู้ 4 (รอผลการตรวจพิสูจน์ร่องรอยบาดแผลและเวลา)'}</div>
        </div>
        <div class="timeline-event-node">
          <span class="timeline-node-time">20:30–20:45</span>
          <span class="timeline-node-title">ตู้เสบียง & ห้องคนไข้</span>
          <div class="timeline-node-sub">${hasPatientWitness ? '✓ ผู้ป่วยยืนยันว่าหมอเพิ่งมาถึงตอน 20:30 (ผิดจากบันทึก)' : 'ตู้เสบียง & ห้องคนไข้ · หมอลิโอราอ้างว่าเฝ้าผู้ป่วยตลอดช่วงอุโมงค์ (รอสอบปากคำคนไข้)'}</div>
        </div>
        <div class="timeline-event-node">
          <span class="timeline-node-time">20:45</span>
          <span class="timeline-node-title">สถานีฮัลเบิร์ด (ออกขบวน)</span>
          <div class="timeline-node-sub">${hasVincentTicket ? 'วินเซนต์ขึ้นรถไฟที่ตู้ 6 · นรินทร์ เวล ก้าวขึ้นรถไฟ พบกิเดียนที่ตู้เลานจ์' : 'นรินทร์ เวล ก้าวขึ้นรถไฟ พบกิเดียนที่ตู้เลานจ์'}</div>
        </div>
        <div class="timeline-event-node">
          <span class="timeline-node-time">21:15–21:18</span>
          <span class="timeline-node-title">ไฟบนขบวนดับวูบ</span>
          <div class="timeline-node-sub">${hasVincentConfession ? 'วินเซนต์ตัดไฟเพื่อขโมยเอกสาร และสะดุดศพในความมืด' : (hasVincentCutters ? 'พบรอยตัดสายไฟหลักในตู้สัมภาระ (ยังไม่ทราบสาเหตุ)' : 'ไฟบนขบวนดับวูบลงชั่วขณะ (ยังไม่ทราบสาเหตุ)')}</div>
        </div>
        <div class="timeline-event-node">
          <span class="timeline-node-time">21:20</span>
          <span class="timeline-node-title">พบศพ & รายงานชันสูตร</span>
          <div class="timeline-node-sub">${hasCase03LioraContradicted ? 'พบศพ · รายงานชันสูตรขัดแย้งกับหลักฐานสารพิษ' : 'พบศพแคสเซียน รีด · ดร. ลิโอรา เข้าตรวจสอบสภาพศพเบื้องต้น'}</div>
        </div>
        <div class="timeline-event-node active-node">
          <span class="timeline-node-time">21:30</span>
          <span class="timeline-node-title">เริ่มการสืบสวน</span>
          <div class="timeline-node-sub">เหลือ 90 นาทีก่อนรถไฟถึงสถานีปลายทางเวสต์มาร์ช</div>
        </div>
      `;
    } else {
      rail.innerHTML = `
        <div class="timeline-event-node">
          <span class="timeline-node-time">20:10–20:35</span>
          <span class="timeline-node-title">สถานีฮัลเบิร์ด (ชานชาลา)</span>
          <div class="timeline-node-sub">${hasCase01VincentCleared ? '✓ วินเซนต์อยู่ที่เคาน์เตอร์สถานี มีใบรับรองยืนยัน' : 'วินเซนต์อ้างว่าอยู่ที่สถานีฮัลเบิร์ด (รอตรวจสอบ)'}</div>
        </div>
        <div class="timeline-event-node ${hasWatch ? 'critical-node' : ''}">
          <span class="timeline-node-time">20:20–20:26</span>
          <span class="timeline-node-title">รถไฟวิ่งผ่านอุโมงค์ · ห้องตู้ 4</span>
          <div class="timeline-node-sub">${hasWatch ? '⚡ แคสเซียนถูกทำร้าย กลไกนาฬิกาพกหยุดเดินที่ 20:25' : 'ช่วงเวลาที่คาดว่าเกิดเหตุในห้องพักตู้ 4 (รอตรวจสอบ)'}</div>
        </div>
        <div class="timeline-event-node">
          <span class="timeline-node-time">20:45</span>
          <span class="timeline-node-title">สถานีฮัลเบิร์ด (ออกขบวน)</span>
          <div class="timeline-node-sub">นรินทร์ เวล ก้าวขึ้นรถไฟ พบกิเดียนที่ตู้เลานจ์</div>
        </div>
        <div class="timeline-event-node ${hasWallClock || hasVincentConfession ? 'active-node' : ''}">
          <span class="timeline-node-time">21:15–21:18</span>
          <span class="timeline-node-title">ไฟบนขบวนดับวูบ</span>
          <div class="timeline-node-sub">${hasWallClock || hasVincentConfession ? (hasWallClock ? 'นาฬิกาไฟฟ้าตู้ 4 หยุดที่ 21:15' : 'สายไฟหลักถูกตัด') + (hasGideonAlibi ? ' · กิเดียนอยู่กับคุณที่เลานจ์' : '') : 'ไฟบนขบวนดับวูบลงชั่วขณะ (ยังไม่ทราบสาเหตุ)'}</div>
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
    }
    container.append(rail);

    // 4. Suspect Alibi & Contradiction Cards
    const suspectsGrid = document.createElement('div');
    suspectsGrid.className = 'timeline-suspects-grid';

    // Gideon Card
    const gideonCard = document.createElement('div');
    gideonCard.className = 'timeline-suspect-card';
    let gideonStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
    let gideonAlibiText = '“ตอนไฟดับคุณอยู่กับผม คุณยืนยันให้ผมได้”';
    let gideonFindings = 'กิเดียนอ้างว่าอยู่กับคุณตอนไฟดับ 21:15 กำลังรอหลักฐานยืนยันว่าช่วงเกิดเหตุที่แท้จริงเกิดขึ้นเมื่อใด';

    if (caseId === 'case_02_vincent') {
      gideonAlibiText = '“ผมคุยกับคุณในตู้เลานจ์ตั้งแต่สถานีฮัลเบิร์ดจนกระทั่งเกิดเรื่อง”';
      if (hasCase02GideonVerified) {
        gideonStampHtml = '<span class="dossier-stamp stamp-verified">ยืนยันแล้ว / VERIFIED</span>';
        gideonFindings = 'พ้นข้อหาฆาตกรรม! เมื่อยืนยันว่าเหตุเกิดช่วงไฟดับ 21:15–21:18 น. นรินทร์นั่งคุยกับกิเดียนในตู้เลานจ์ตลอดช่วงดังกล่าว กิเดียนจึงมีพยานที่อยู่สมบูรณ์';
      } else if (hasGideonAlibi) {
        gideonStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
        gideonFindings = 'กิเดียนให้การว่าคุยกับคุณในตู้เลานจ์ตลอดช่วงเกิดเหตุ รอการพิสูจน์ช่วงเวลาเกิดเหตุที่แน่นอน';
      } else {
        gideonStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
        gideonFindings = 'กิเดียนนั่งอยู่ในตู้เลานจ์ รอการสอบปากคำและตรวจสอบช่วงเวลาเกิดเหตุที่แท้จริง';
      }
    } else if (caseId === 'case_03_liora') {
      gideonAlibiText = '“ผมไม่ได้แตะต้องมีดเปิดจดหมาย และไม่ได้ไปห้องแคสเซียนหลังขึ้นรถไฟ”';
      if (hasCase03GideonCleared) {
        gideonStampHtml = '<span class="dossier-stamp stamp-verified">ยืนยันแล้ว / VERIFIED</span>';
        gideonFindings = 'พ้นข้อหาฆาตกรรม! เมื่อพิสูจน์ได้ว่าแคสเซียนเสียชีวิตจากสารพิษตั้งแต่ช่วงอุโมงค์ (20:25) บาดแผลจากมีดเป็นเพียงการจัดฉากอำพรางในภายหลัง';
      } else if (hasBurntC || hasDossierC) {
        gideonStampHtml = '<span class="dossier-stamp stamp-suspect">ต้องสงสัย / SUSPECTED</span>';
        gideonFindings = 'พบร่องรอยเอกสารที่ถูกเผาและแรงจูงใจเรื่องแฟ้มคดี รอผลพิสูจน์สาเหตุการตายที่แท้จริงและอาวุธ';
      } else {
        gideonStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
        gideonFindings = 'กิเดียนอ้างว่าไม่ได้แตะต้องมีดและไม่ได้เข้าใกล้ผู้ตาย รอผลพิสูจน์สาเหตุการตายที่แท้จริงและอาวุธ';
      }
    } else {
      if (hasCase01GideonContradicted) {
        gideonStampHtml = '<span class="dossier-stamp stamp-contradiction">หักล้างแล้ว / CONTRADICTION</span>';
        gideonFindings = 'คำอ้างช่วงไฟดับ (21:15) ไร้ผล! เหตุฆาตกรรมเกิดช่วง 20:20–20:26 ซึ่งกิเดียนยอมรับว่าอยู่คนเดียวและไม่มีพยานยืนยันที่อยู่';
        if (hasStaffNoMsg) {
          gideonFindings += '<br><strong style="color:#e5a440;">[เจตนาลวง / FABRICATION]</strong> พนักงานยืนยันว่าไม่เคยฝากข่าวเลื่อนนัด กิเดียนสร้างเรื่องเท็จเพื่อรั้งตัวคุณไว้ที่เลานจ์';
        }
        if (hasBurntC && hasDossierC) {
          gideonFindings += '<br><strong style="color:#ee6b54;">[พบแรงจูงใจ / MOTIVE]</strong> เศษเอกสารที่เผามีลายเซ็น G.H. เพื่อทำลายความรับผิดในคดีเบลล์เวเธอร์';
        }
      } else if (hasGideonAlibi) {
        gideonStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
        gideonFindings = 'กิเดียนอ้างว่าอยู่กับคุณตอนไฟดับ 21:15 กำลังรอหลักฐานยืนยันว่าช่วงเกิดเหตุที่แท้จริงเกิดขึ้นเมื่อใด';
      }
    }

    gideonCard.innerHTML = `
      <div class="timeline-card-header">
        <span class="timeline-suspect-name">กิเดียน ฮาร์ต (Gideon Hart)</span>
        ${gideonStampHtml}
      </div>
      <div class="timeline-alibi-claim">${gideonAlibiText}</div>
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
    let vincentAlibiText = '“ผมตัดสายไฟตอนสามทุ่มสิบห้า แต่ผมไม่ได้ฆ่าเขา”';
    let vincentFindings = 'วินเซนต์นั่งเงียบอยู่ตู้ 6 มีพิรุธและท่าทางวิตกกังวล รอตรวจสอบประวัติและเวลาที่ขึ้นรถไฟ';

    if (caseId === 'case_02_vincent') {
      vincentAlibiText = '“ผมเข้าไปในห้องตอนไฟดับจริง แต่แคสเซียนถูกฆ่าอยู่ก่อนแล้ว ผมแค่สะดุดศพ”';
      if (hasCase02VincentContradicted) {
        vincentStampHtml = '<span class="dossier-stamp stamp-contradiction">หักล้างแล้ว / CONTRADICTION</span>';
        vincentFindings = 'คำให้การถูกหักล้างสิ้นเชิง! คราบเลือดบนเสื้อโค้ตเป็นรอยกระเซ็นแรงสูง (Arterial Spatter) จากการจ้วงแทง ไม่ใช่รอยสะดุดสัมผัส และร่องฟันคีมตัดสายไฟตรงกับตู้ไฟสัมภาระ';
        if (hasMaraJob || deductionSet.has('D03_VINCENT_MOTIVE')) {
          vincentFindings += '<br><strong style="color:#ee6b54;">[พบแรงจูงใจ / MOTIVE]</strong> พบบันทึกจ้างงานชิงเอกสารจากมารา วอสส์ แลกกับเงินรางวัลก้อนโต';
        }
      } else if (hasVincentCutters || hasVincentConfession || hasVincentBlood) {
        vincentStampHtml = '<span class="dossier-stamp stamp-suspect">ต้องสงสัย / SUSPECTED</span>';
        vincentFindings = 'ยอมรับว่าตัดไฟหรือพบคราบเลือดและเครื่องมือ รอผลตรวจพิสูจน์รอยกระเซ็นของเลือดและอาวุธมีด';
      } else {
        vincentStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
        vincentFindings = 'วินเซนต์นั่งเงียบอยู่ตู้ 6 มีพิรุธและท่าทางวิตกกังวล รอผลตรวจพิสูจน์คราบเลือดและเครื่องมือ';
      }
    } else if (caseId === 'case_03_liora') {
      vincentAlibiText = '“ผมแค่ตัดไฟจะขโมยกระเป๋าแต่สะดุดศพในความมืด เลือดเลยเปื้อนเสื้อ”';
      if (hasCase03VincentCleared) {
        vincentStampHtml = '<span class="dossier-stamp stamp-verified">พ้นข้อหาฆาตกรรม / EXCULPATED</span>';
        vincentFindings = 'วินเซนต์เป็นเพียงแพะรับบาป! ตั๋วรถไฟยืนยันว่าเขาขึ้นที่ฮัลเบิร์ด (20:45) หลังแคสเซียนเสียชีวิตจากยาพิษไปแล้ว (20:25) คราบเลือดเกิดจากการสะดุดศพในความมืด';
      } else if (hasVincentBlood || hasVincentCutters || hasVincentConfession) {
        vincentStampHtml = '<span class="dossier-stamp stamp-suspect">ต้องสงสัย / SUSPECTED</span>';
        vincentFindings = 'ตกเป็นผู้ต้องสงสัยอันดับหนึ่งเพราะคราบเลือดและคีมตัดไฟ รอหลักฐานพิสูจน์สาเหตุการตายที่แท้จริงและเวลาที่ขึ้นรถไฟ';
      } else {
        vincentStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
        vincentFindings = 'วินเซนต์ถูกเพ่งเล็งเรื่องคราบเลือดและเหตุไฟดับ รอหลักฐานพิสูจน์สาเหตุการตายและลำดับเวลา';
      }
    } else {
      if (hasCase01VincentCleared) {
        vincentStampHtml = '<span class="dossier-stamp stamp-verified">ยืนยันแล้ว / VERIFIED</span>';
        vincentFindings = 'พ้นข้อหาฆาตกรรม! ตั๋วรถไฟและใบรับรองของนายสถานียืนยันว่าเขาอยู่ที่เคาน์เตอร์สถานีฮัลเบิร์ดช่วง 20:10–20:35 จึงไม่อาจอยู่ในห้องเกิดเหตุช่วง 20:20–20:26 ได้';
        if (hasVincentConfession) {
          vincentFindings += ' (เขายอมรับว่าตัดสายไฟตอน 21:15 เพื่อขโมยกระเป๋าเท่านั้น)';
        }
      } else if (hasVincentConfession || hasVincentCutters || hasVincentBlood) {
        vincentStampHtml = '<span class="dossier-stamp stamp-suspect">ต้องสงสัย / SUSPECTED</span>';
        vincentFindings = 'พบหลักฐานการตัดสายไฟหรือคราบเลือด จำเป็นต้องหาหลักฐานยืนยันที่อยู่ช่วง 20:20–20:26 เพื่อพิสูจน์ความบริสุทธิ์';
      }
    }

    vincentCard.innerHTML = `
      <div class="timeline-card-header">
        <span class="timeline-suspect-name">วินเซนต์ เกรย์ (Vincent Gray)</span>
        ${vincentStampHtml}
      </div>
      <div class="timeline-alibi-claim">${vincentAlibiText}</div>
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
    let lioraAlibiText = '“ฉันอยู่ดูแลผู้ป่วยที่ตู้เสบียงตลอดช่วงรถไฟวิ่งในอุโมงค์”';
    let lioraFindings = 'ดร. ลิโอรา อ้างว่าดูแลผู้ป่วยที่ตู้ 3 กำลังรอตรวจสมุดบันทึกในห้องแพทย์และสอบถามผู้ป่วย';

    if (caseId === 'case_02_vincent') {
      lioraAlibiText = '“ฉันชันสูตรศพทันทีที่ไฟติด อุณหภูมิร่างกายและสภาพแผลยืนยันเวลาตายช่วงไฟดับ”';
      if (hasCase02LioraCleared) {
        lioraStampHtml = '<span class="dossier-stamp stamp-verified">ยืนยันแล้ว / VERIFIED</span>';
        lioraFindings = 'พ้นข้อหาฆาตกรรม! พยานผู้ป่วยในตู้ 3 ยืนยันว่า ดร. ลิโอรา อยู่ดูแลคนไข้ตลอดช่วงไฟดับ และผลการตรวจชันสูตรตรงกับสภาพศพจริง';
      } else {
        lioraStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
        lioraFindings = 'ดร. ลิโอรา ให้การเบื้องต้นเกี่ยวกับสภาพศพ รอการตรวจสอบพยานที่อยู่ของผู้ป่วยในตู้ 3 เพื่อยืนยันว่าเธอไม่ได้อยู่ในห้องเกิดเหตุ';
      }
    } else if (caseId === 'case_03_liora') {
      lioraAlibiText = '“ฉันอยู่ดูแลผู้ป่วยตั้งแต่สองทุ่ม และผู้ตายเพิ่งถูกแทงตายตอนไฟดับสามทุ่มสิบห้า”';
      if (hasCase03LioraContradicted) {
        lioraStampHtml = '<span class="dossier-stamp stamp-contradiction">หักล้างแล้ว / CONTRADICTION</span>';
        lioraFindings = 'การอำพรางทางการแพทย์ถูกเปิดโปง! แผลแทงไม่มีการตอบสนองของสิ่งมีชีวิต (Post-mortem) ในถ้วยชามีสารพิษ และตรวจพบการปลอมแปลงบันทึกการรักษา';
        if (hasPatientWitness) {
          lioraFindings += '<br><strong style="color:#ee6b54;">[พยานหักล้าง]</strong> ผู้ป่วยตู้ 3 ยืนยันว่าหมอลิโอราเพิ่งมาถึงตอน 20:30 น. หลังเหตุการณ์ในอุโมงค์จบลงแล้ว';
        }
      } else if (hasTeaTrace || hasLioraLog || hasPatientWitness) {
        lioraStampHtml = '<span class="dossier-stamp stamp-suspect">ต้องสงสัย / SUSPECTED</span>';
        lioraFindings = 'พบพิรุธในสมุดบันทึกหรือพยานคนไข้ รอหลักฐานเชื่อมโยงสารพิษและเวลาเข้าเวรเพื่อหักล้างคำให้การอย่างสมบูรณ์';
      } else {
        lioraStampHtml = '<span class="dossier-stamp stamp-pending">รอตรวจสอบ</span>';
        lioraFindings = 'ดร. ลิโอรา อ้างว่าดูแลผู้ป่วยตลอดช่วงเวลาเกิดเหตุและชันสูตรว่าตายจากแผลแทง รอตรวจสอบสมุดบันทึกและพยานคนไข้';
      }
    } else {
      if (hasCase01LioraCleared) {
        lioraStampHtml = '<span class="dossier-stamp stamp-verified">ยืนยันแล้ว / VERIFIED</span>';
        lioraFindings = 'พ้นข้อหาฆาตกรรม! สมุดบันทึกการรักษาในห้องแพทย์และคำให้การของผู้ป่วยตู้ 3 สอดคล้องกัน ยืนยันว่าเธออยู่ดูแลคนไข้ตลอดช่วงที่รถไฟวิ่งในอุโมงค์ (20:20–20:26)';
      } else if (evidenceSet.has('secret_file') || evidenceSet.has('liora_time_hesitation')) {
        lioraStampHtml = '<span class="dossier-stamp stamp-suspect">ต้องสงสัย / SUSPECTED</span>';
        lioraFindings = 'พบแฟ้มคดีเก่าของครอบครัวและท่าทีลังเล จำเป็นต้องตรวจสอบพยานคนไข้เพื่อยืนยันที่อยู่';
      }
    }

    lioraCard.innerHTML = `
      <div class="timeline-card-header">
        <span class="timeline-suspect-name">ดร. ลิโอรา เวนน์ (Dr. Liora Venn)</span>
        ${lioraStampHtml}
      </div>
      <div class="timeline-alibi-claim">${lioraAlibiText}</div>
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

    // Chat history is already on the page and does not depend on /journal.
    if (activeTab === 'chat') {
      renderChatTab(wrap);
      return;
    }

    if (!data) {
      wrap.append(empty('กำลังเปิดแฟ้มคดี', 'รอสักครู่…'));
      return;
    }

    if (activeTab === 'people') {
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

      if (typeof updateProfilerHUD === 'function' && data.profile) {
        updateProfilerHUD(data.profile);
      }
      if (typeof updateCaseEdition === 'function' && data.case_id) {
        updateCaseEdition(data.case_id);
      }

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

      // Visible objects and locally available dialogue topics in the scene strip.
      const visible = $('visibleObjects');
      if (visible) {
        visible.replaceChildren();

        // 1. Profiler Assistance Chip (ระดับ 2: เมื่อติดหล่มหรือวนซ้ำซ้อน)
        const assistanceChip = data.profile?.assistance_chip || (typeof latestProfile !== 'undefined' ? latestProfile?.assistance_chip : null);
        if (assistanceChip && !(typeof gameOver !== 'undefined' && gameOver)) {
          const profilerBtn = document.createElement('button');
          profilerBtn.type = 'button';
          profilerBtn.className = 'object-button profiler-chip-btn';
          profilerBtn.title = assistanceChip.label || `คำแนะนำจาก Profiler: ${assistanceChip.command}`;
          profilerBtn.innerHTML = `<span class="chip-lens">💡</span> ${assistanceChip.label || assistanceChip.command}`;
          profilerBtn.onclick = () => fillInput(assistanceChip.command);
          visible.append(profilerBtn);
        }

        // 2. สภาวะปกติ (Normal State): แสดงเฉพาะตัวอย่างคำสั่งพื้นฐาน 1-2 ปุ่ม ไม่ปล่อยปุ่มทั้งหมดจนคลิกจบเกมได้เอง
        let sampleButtonsCount = 0;

        // ตัวอย่างคำสั่งตรวจสิ่งของ (สูงสุด 1 ปุ่ม)
        if (data.visible && data.visible.length && sampleButtonsCount < 2) {
          const o = data.visible[0];
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'object-button quick-inspect-btn';
          btn.title = `ตัวอย่างคำสั่ง: ตรวจ${o.name}`;
          btn.innerHTML = `<span class="chip-lens">🔍</span> ตรวจ${o.name}`;
          btn.onclick = () => fillInput(`ตรวจ${o.name}`);
          visible.append(btn);
          sampleButtonsCount++;
        }

        const peopleHere = (data.people || []).filter(person => {
          const isEnc = Boolean(
            person.encountered !== undefined
              ? person.encountered
              : (person.discovered !== undefined
                ? person.discovered
                : (person.here || (gameState?.visited_locations && gameState.visited_locations.includes(person.location)) || person.interrogated))
          );
          return person.here && isEnc;
        });

        if (peopleHere.length && sampleButtonsCount < 2) {
          for (let pi = 0; pi < peopleHere.length && sampleButtonsCount < 2; pi++) {
            const person = peopleHere[pi];
            const personName = person.name.split(' (')[0];
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'object-button quick-talk-btn';
            if (person.topics && person.topics.length) {
              const topic = person.topics[0];
              btn.title = `ตัวอย่างคำสั่ง: ถาม ${personName} เรื่อง${topic.label}`;
              btn.textContent = `🗣 ${personName} · ${topic.label}`;
              btn.onclick = () => fillInput(`สอบปากคำ ${personName} เรื่อง ${topic.label}`);
            } else {
              btn.title = `ตัวอย่างคำสั่ง: สอบปากคำ ${personName}`;
              btn.textContent = `🗣 สอบปากคำ ${personName}`;
              btn.onclick = () => fillInput(`สอบปากคำ ${personName}`);
            }
            visible.append(btn);
            sampleButtonsCount++;
          }
        }

        if (!visible.children.length) {
          const emptySpan = document.createElement('span');
          emptySpan.className = 'muted';
          emptySpan.textContent = typeof gameOver !== 'undefined' && gameOver ? 'คดีปิดแล้ว' : 'พิมพ์คำสั่งเพื่อสำรวจ หรือใช้คำสั่งตรวจ/สนทนา';
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
