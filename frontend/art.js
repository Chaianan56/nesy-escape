/* Images illustrate server-approved actions; they never move the player or grant evidence. */
const GameArt = (() => {
  const rooms = {
    locomotive:'scene-01-locomotive', luggage_van_electrical:'scene-02-electrical',
    dining_car_staff:'scene-03-dining', first_class_car:'scene-04-crime',
    lounge_car:'scene-05-lounge', second_class_car:'scene-06-second-class'
  };
  const people = {gideon_hart:'scene-05-lounge',vincent_gray:'scene-06-second-class',dr_liora_venn:'scene-04-medical',car_attendant:'scene-03-dining',patient_witness:'scene-03-dining'};
  const endings = {true_ending:'ending-true',cold_justice:'ending-incomplete',the_scapegoat:'ending-scapegoat',the_paranoia_trap:'ending-paranoia',unproven:'ending-unproven',cold_arrival:'ending-arrival'};
  const evidence = {};
  const groups = {
    'detail-electrical-controls':['power_panel','fuse_box','backup_switch'],
    'detail-cut-wire':['cut_copper_wire','tool_marks'], 'detail-electrical-log':['maintenance_log'],
    'detail-patient-log':['liora_patient_log'], 'detail-pocket-watch':['pocket_watch'],
    'detail-burnt-paper':['burnt_folder_c'], 'detail-teacups':['second_teacup','tea_lozenge_trace'],
    'detail-wax':['wax_seal_imprint'], 'detail-cufflink-soot':['obsidian_cufflink','red_soot'],
    'detail-dossier':['dossier_missing_file_c','judicial_transfer_order','dossier_bag','case_year_note','mara_job_note','file_c_initials'], 'detail-wall-clock':['wall_clock'],
    'detail-medical-file':['secret_file'], 'medical-key-v2':['medical_key'],
    'scene-04-crime':['letter_opener'],
    'scene-02-electrical':['electrical_room_door'],
    'detail-gideon':['gideon_lozenge_tin','gideon_signet_ring','gideon_missing_button','gideon_sleeve_soot'],
    'detail-vincent':['wire_cutters','vincent_blood','vincent_ticket'],
    'scene-03-dining':['staff_key','liora_patient_witness','staff_impact_testimony','staff_service_record','staff_no_message','vincent_station_alibi'],
    'scene-05-lounge':['gideon_blackout_alibi','gideon_no_early_alibi','postponed_meeting_claim'],
    'scene-06-second-class':['vincent_body_testimony','vincent_blackout_confession','vincent_theft_motive'],
    'scene-04-medical':['liora_time_estimate','liora_medical_access','liora_time_hesitation','medical_room_door']
  };
  Object.entries(groups).forEach(([asset,ids])=>ids.forEach(id=>evidence[id]=asset));
  let selected=null, location=null, shown=null;
  function source(asset){return `/game-art/${asset}.png`;}
  function onResult(result){
    const state=result.new_state, command=result.parsed;
    if(!state || !command)return;
    if(!result.decision?.allowed){
      if(command.action==='move'&&command.target==='locomotive') selected={asset:rooms.locomotive,label:'ทางเข้าเขตหวงห้าม · คุณยังอยู่ตู้เดิม'};
      return;
    }
    if(location && location !== state.current_location){
      selected = null;
    }
    location=state.current_location;
    if(command.action==='move') selected={asset:rooms[location],label:'ภาพฉากผ่านสายตาผู้เล่น'};
    else if(command.action==='interrogate' || (command.action==='examine'&&people[command.target])) selected={asset:people[command.target]||rooms[location],label:'สนทนาและตรวจสอบบุคคล'};
    else if(command.action==='examine'){
      const asset=evidence[command.target]||rooms[command.target];
      if(asset)selected={asset,label:evidence[command.target]?'ภาพประกอบหลักฐาน · รายละเอียดอยู่ในข้อความ':'ภาพฉากผ่านสายตาผู้เล่น'};
      else selected={asset:rooms[location],label:'ภาพฉากผ่านสายตาผู้เล่น'};
    }
    else if(command.action==='sequence'){
      selected={asset:rooms[location],label:'ภาพฉากผ่านสายตาผู้เล่น'};
    }
    else if(command.action==='take'){
      const asset=evidence[command.target];
      selected={asset:asset||rooms[location],label:asset?'ภาพประกอบหลักฐาน · รายละเอียดอยู่ในข้อความ':'ภาพฉากผ่านสายตาผู้เล่น'};
    }
  }
  function setStepScene(action, target, stepLocation){
    const loc = stepLocation || location;
    location = loc;
    let view = null;
    if (action === 'move') {
      view = { asset: rooms[loc] || rooms[target] || rooms.dining_car_staff, label: 'ภาพฉากผ่านสายตาผู้เล่น' };
    } else if (action === 'interrogate' || people[target]) {
      view = { asset: people[target] || rooms[loc], label: 'สนทนาและตรวจสอบบุคคล' };
    } else if (evidence[target]) {
      view = { asset: evidence[target], label: 'ภาพประกอบหลักฐาน · รายละเอียดอยู่ในข้อความ' };
    } else {
      view = { asset: rooms[loc] || rooms.lounge_car, label: 'ภาพฉากผ่านสายตาผู้เล่น' };
    }
    selected = view;
    const img = document.getElementById('sceneImage');
    if (!img || !view.asset) return;
    const sceneLabel = document.getElementById('sceneLabel');
    if (sceneLabel) sceneLabel.textContent = view.label;
    if (shown === view.asset) return;
    shown = view.asset;
    const status = document.getElementById('artStatus');
    if (status) { status.hidden = false; status.textContent = 'กำลังโหลดภาพ…'; }
    img.onload = () => { if (status) status.hidden = true; };
    img.onerror = () => { if (status) { status.hidden = false; status.textContent = 'โหลดภาพไม่สำเร็จ · ยังอ่านข้อมูลและพิมพ์เล่นต่อได้'; } };
    img.alt = view.label;
    img.src = source(view.asset);
  }
  function sync(state){
    if(!state)return;
    if(location!==state.current_location){location=state.current_location;selected=null;}
    const ending=endings[state.ending_id];
    const view=ending?{asset:ending,label:'บทสรุปคดี'}:selected||{asset:rooms[location],label:'ภาพฉากผ่านสายตาผู้เล่น'};
    const img=document.getElementById('sceneImage');
    if(!img||!view.asset)return;
    document.getElementById('sceneLabel').textContent=view.label;
    if(state.ending_id)document.getElementById('sceneStatus').textContent='คดีปิดแล้ว';
    if(shown===view.asset)return;
    shown=view.asset;
    const status=document.getElementById('artStatus');status.hidden=false;status.textContent='กำลังโหลดภาพ…';
    img.onload=()=>{status.hidden=true;};
    img.onerror=()=>{status.hidden=false;status.textContent='โหลดภาพไม่สำเร็จ · ยังอ่านข้อมูลและพิมพ์เล่นต่อได้';};
    img.alt=view.label;img.src=source(view.asset);
  }
  function journalImage(id,name){
    if(!evidence[id])return null;
    const img=document.createElement('img');img.className='evidence-image';img.alt=`ภาพประกอบ ${name}`;
    img.loading='lazy';img.decoding='async';img.src=source(evidence[id]);
    img.onerror=()=>{img.hidden=true;};return img;
  }
  function journalPersonImage(id,name){
    if(!people[id])return null;
    const img=document.createElement('img');img.className='archive-person-image';img.alt=`ภาพของ ${name}`;
    img.loading='lazy';img.decoding='async';img.src=source(people[id]);
    img.onerror=()=>{img.hidden=true;};return img;
  }
  return {onResult,sync,journalImage,journalPersonImage,setStepScene};
})();

