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
      title: "เศษคำสั่งที่ถูกเผา (Burnt Memo BW-C/17)",
      date: "16 พฤศจิกายน 1923",
      classification: "ลับเฉพาะส่วนกลาง · สำเนาไฟไหม้บางส่วน",
      summary: "พบในถาดเขี่ยบุหรี่ห้องแคสเซียน ปรากฏรหัส [G.H.] สั่งแยกโทรเลขเตือนออกจากสำนวน",
      content: `เศษกระดาษพับซ้อนในถาดอ่านได้ว่า “BW-C/17 — 16 พฤศจิกายน 1923 — ให้แยกโทรเลขเตือนและคำให้การเรื่องคำสั่งส่วนกลางออกจากชุดสอบสวน...” และส่วนลงนาม G.H. ส่วนอื่นไหม้จนอ่านไม่ได้ เลขเอกสารสามารถเทียบสารบัญในกระเป๋าได้\n\nรอยไหม้อยู่ตามขอบและรอยพับ ไม่มีข้อความส่วนที่หายไปให้เดาเติม การระบุผู้ลงนามต้องตรวจเทียบเลขเอกสารกับทะเบียนในกระเป๋าสำนวน`,
    },
    {
      id: "autopsy_report",
      title: "บันทึกตรวจร่างเบื้องต้น (Autopsy Report)",
      date: "14 พฤศจิกายน 1938 · 21:20 น.",
      classification: "รายงานชันสูตรเบื้องต้น · แพทย์ประจำขบวน",
      summary: "แพทย์หญิงลิโอรา เวนน์ ตรวจพบแผลของมีคม เลือดเริ่มเย็นตัวก่อนฮีตเตอร์ดับ",
      content: `14 พฤศจิกายน 1938 หลังพบร่างราว 21:20 — ผู้ตรวจ: ลิโอรา เวนน์\n\nพบบาดแผลจากของคมและร่องรอยต่อสู้ มีดเปิดจดหมายใกล้ร่างสอดคล้องกับลักษณะอาวุธที่ต้องตรวจเพิ่มเติม ยังไม่มีผลตรวจลายนิ้วมือหรือผลห้องปฏิบัติการบนขบวน\n\nการตรวจครั้งนี้ไม่ระบุเวลาตายเป็นนาทีหรือยืนยันว่าเสียชีวิตขณะไฟดับ ผู้สืบสวนต้องตรวจลำดับเหตุการณ์จากฉากและพยานร่วมกัน`,
    },
    {
      id: "secret_file",
      title: "แฟ้มรักษาและคำให้การเอเลียส เวนน์ (Project Nocturne)",
      date: "14 พฤศจิกายน 1923 – 1931",
      classification: "เวชระเบียนส่วนบุคคล · คำให้การที่ถูกตัดออก",
      summary: "บิดาของลิโอราให้การเรื่องคำสั่งส่วนกลางให้เดินรถต่อแม้มีคำเตือน",
      content: `เอเลียส เวนน์ รอดจากเหตุ 14 พฤศจิกายน 1923 เขาให้การระหว่างรักษาว่ามีคำเตือนก่อนออกขบวนและมีคำสั่งให้เดินต่อ คำให้การนี้ไม่อยู่ในสำนวนเผยแพร่ บันทึกสุดท้ายระบุเสียชีวิตด้วยโรคประจำตัวในสถานบำบัดปี 1931 ลิโอราเก็บแฟ้มเพื่อคืนความน่าเชื่อถือให้พ่อ ไม่ได้เป็นหลักฐานว่าผู้ใดฆ่าแคสเซียนคืนนี้\n\nสำเนาคำให้การระหว่างพักรักษา: “เราได้รับคำเตือนให้รอยืนยันเส้นทาง แต่มีคำสั่งจากส่วนกลางให้เดินต่อ”\n\nเอกสารแนบระบุว่าคำให้การนี้ถูกนำออกจากสำนวนฉบับเผยแพร่ แฟ้มไม่มีข้อมูลว่าใครอยู่ในห้องแคสเซียนคืนนี้`,
    },
    {
      id: "dossier_missing_file_c",
      title: "สำเนาโทรเลขเตือนจากเบลล์เวเธอร์ (Voss Telegram Draft)",
      date: "14 พฤศจิกายน 1923",
      classification: "ร่างโทรเลขสถานีรถไฟเบลล์เวเธอร์",
      summary: "นายสถานีแอนเซลม์ วอสส์ ขอให้หยุดขบวนพิเศษก่อนเกิดโศกนาฏกรรม",
      content: `14 พฤศจิกายน 1923\nจาก แอนเซลม์ วอสส์ นายสถานีเบลล์เวเธอร์\n\nขอให้หยุดรอการยืนยันว่าเส้นทางปลอดภัยก่อนปล่อยขบวนพิเศษ Nocturne\n\nสำเนาอยู่ในแฟ้ม B ร่วมกับสมุดบันทึกต้นฉบับของนายสถานีที่มาราให้แคสเซียนยืมตรวจ เลขรับส่งใช้เทียบทะเบียน ไม่ใช่คำยืนยันว่าใครสังหารแคสเซียนในปี 1938`,
    }
  ];

  let data = null, activeTab = 'chat', revision = 0;

  function button(label, command, className = 'object-button') {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = className;
    b.textContent = label;
    b.onclick = () => {
      document.getElementById('casebookDialog')?.close();
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

  function drawScene(location) {
    if (typeof GameArt !== 'undefined' && GameArt.sync) {
      GameArt.sync(gameState || { current_location: location });
    }
  }

  // Interactive Train Map
  function map() {
    const wrap = $('trainCars');
    if (!wrap) return;
    wrap.replaceChildren();

    rooms.forEach(([id, label, fullDesc], i) => {
      const isCurrent = gameState?.current_location === id;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'car' + (isCurrent ? ' active' : '');
      b.title = isCurrent ? `คุณยืนอยู่ที่นี่: ${label}` : `คลิกเพื่อเดินทางไปที่ ${label}`;
      b.setAttribute('aria-label', i === 0 ? 'หัวรถจักร พื้นที่หวงห้าม' : `ตู้ ${label}`);
      if (isCurrent) b.setAttribute('aria-current', 'location');

      b.innerHTML = `
        <div class="car-body">
          <div class="car-windows"><i></i><i></i><i></i><i></i></div>
          ${isCurrent ? '<span class="car-pin">📍</span>' : ''}
        </div>
      `;

      const name = document.createElement('span');
      name.className = 'car-name';
      name.textContent = `${String(i + 1).padStart(2, '0')} · ${label}`;
      b.append(name);

      b.onclick = () => {
        if (typeof gameOver !== 'undefined' && gameOver) return;
        if (isCurrent) {
          fillInput('ดูรอบๆ');
        } else {
          fillInput(`ไปตู้ ${i + 1}`);
        }
      };

      wrap.append(b);
    });
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
        chip.innerHTML = `<strong>${item.name}</strong><small>${item.description || ''}</small>`;
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
    let hasDocs = false;

    IN_GAME_DOCUMENTS.forEach(doc => {
      const isFound = discoveredIds.has(doc.id) || (data.background && data.background.length > 0);
      hasDocs = true;
      const card = document.createElement('div');
      card.className = 'doc-card' + (isFound ? ' doc-found' : ' doc-locked');
      card.innerHTML = `
        <div class="doc-card-top">
          <span class="doc-card-badge">${doc.classification}</span>
          <span class="doc-card-date">${doc.date}</span>
        </div>
        <strong class="doc-card-title">${doc.title}</strong>
        <p class="doc-card-summary">${doc.summary}</p>
        <div class="doc-card-actions">
          <button type="button" class="chip-btn doc-read-btn">📖 เปิดอ่านฉบับเต็ม</button>
        </div>
      `;
      card.querySelector('.doc-read-btn').onclick = () => openDocument(doc);
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

    wrap.append(docSection);

    // 3. Physical Evidence
    const clueSection = document.createElement('div');
    clueSection.className = 'archive-section';
    clueSection.innerHTML = `<h3 class="archive-section-title">🔍 วัตถุพยานและหลักฐานที่พบ (${data.evidence.length} ชิ้น)</h3>`;

    if (!data.evidence.length) {
      clueSection.append(empty('ยังไม่พบหลักฐาน', 'สำรวจห้อง ตรวจสิ่งของ และสอบถามพยานเพื่อบันทึกหลักฐาน'));
    } else {
      data.evidence.forEach((e, i) => {
        const box = document.createElement('details');
        box.className = 'evidence-card';
        const title = document.createElement('summary');
        const icon = document.createElement('span');
        icon.className = 'clue-icon';
        icon.textContent = String(i + 1).padStart(2, '0');
        title.append(icon, document.createTextNode(e.name));

        const source = document.createElement('small');
        source.className = 'evidence-source';
        source.textContent = `${e.kind === 'testimony' ? '🗣️ คำให้การ' : '🔎 วัตถุพยาน'} · ${e.source || ''} ${e.source_note ? '— ' + e.source_note : ''}`;

        const p = document.createElement('p');
        p.textContent = e.description;

        box.append(title, source, p);

        box.addEventListener('toggle', () => {
          if (box.open && !box.querySelector('img') && typeof GameArt !== 'undefined' && GameArt.journalImage) {
            const image = GameArt.journalImage(e.id, e.name);
            if (image) box.append(image);
          }
        });

        clueSection.append(box);
      });
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

    data.people.forEach(p => {
      const card = document.createElement('div');
      card.className = 'person-card' + (p.here ? ' person-here' : '');

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

      const status = document.createElement('small');
      status.className = 'person-status';
      const roleText = p.accusable === false ? 'พยาน / บุคลากร' : 'ผู้ต้องสงสัย';
      const convoText = p.interrogated ? '✓ เคยสนทนาแล้ว' : 'ยังไม่ได้สนทนา';
      status.textContent = `${roleText} · ${convoText}`;
      card.append(status);

      // Actions
      const actions = document.createElement('div');
      actions.className = 'person-actions';

      if (p.here && (!typeof gameOver !== 'undefined' || !gameOver)) {
        actions.append(button('💬 สอบปากคำ', `สอบปากคำ ${p.name.split(' (')[0]}`));
        (p.topics || []).forEach(topic => {
          actions.append(button(`ถาม: ${topic.label}`, `ถาม${p.name.split(' (')[0]} เรื่อง${topic.label}`));
        });
      } else if (!p.here && p.location && (!typeof gameOver !== 'undefined' || !gameOver)) {
        const carLabel = locationsMap[p.location] || p.location;
        actions.append(button(`🚶 ไปพบที่ ${carLabel}`, `ไปที่ ${p.location}`));
      }

      if (actions.children.length) card.append(actions);

      // Unlocked Testimonies from this person
      const testimonies = data.evidence.filter(e =>
        e.kind === 'testimony' && (
          e.source?.includes(p.name.split(' (')[0]) ||
          e.source_note?.includes(p.name.split(' (')[0]) ||
          (p.id && e.id?.includes(p.id.split('_')[0]))
        )
      );

      if (testimonies.length) {
        const testSection = document.createElement('div');
        testSection.className = 'person-testimonies';
        testSection.innerHTML = `<small class="testimony-label">คำให้การที่บันทึกไว้ (${testimonies.length}):</small>`;
        testimonies.forEach(t => {
          const q = document.createElement('blockquote');
          q.className = 'testimony-quote';
          q.innerHTML = `“${t.description}”<span>— ${t.name}</span>`;
          testSection.append(q);
        });
        card.append(testSection);
      }

      wrap.append(card);
    });
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
