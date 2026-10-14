# Nocturne Express — วิธีตรวจเส้นทางคดีรุ่นใหม่

วันที่ 12 ตุลาคม 2026 · เอกสารเฉลยสำหรับพัฒนาและทดสอบ

เส้นทางที่เครื่องอ่านอยู่ใน `data/walkthrough.json` และ `app/walkthrough.py` ไม่จำเป็นต้องเดินตามนี้เมื่อเล่นปกติ ตัวอย่างด้านล่างใช้คำสั่งตรงที่ระบบรองรับเพื่อให้ตรวจซ้ำได้โดยไม่เสียการเรียกโมเดลตีความภาษา

## 1. เส้นทางแกนกระดุม + ตรา

เริ่มตู้5 โดยมีความทรงจำกิเดียนอยู่ด้วยตอนไฟดับและข่าวเลื่อนนัดแล้ว

```text
interrogate gideon_hart account
move first_class_car
examine pocket_watch
examine red_soot
examine wall_clock
examine case_year_note
unlock dossier_bag 1923
examine dossier_missing_file_c
examine file_c_initials
examine judicial_transfer_order
examine burnt_folder_c
examine obsidian_cufflink
examine wax_seal_imprint
move dining_car_staff
interrogate car_attendant service
interrogate car_attendant impact
examine tunnel_schedule
take staff_key
move luggage_van_electrical
unlock electrical_room_door staff_key
examine maintenance_log
move lounge_car
examine gideon_missing_button
examine gideon_signet_ring
```

จากนั้นเปิดคำถามเรื่องนาฬิกาสองเรือนในสมุดคดี เลือกข้อสรุปว่าเหตุรุนแรงมาก่อนไฟดับ และแนบ7รายการนี้:

1. นาฬิกาพก (`pocket_watch`)
2. เขม่าบนเลือด (`red_soot`)
3. บันทึกอุโมงค์ (`tunnel_schedule`)
4. พนักงานได้ยินเสียง (`staff_impact_testimony`)
5. นาฬิกาผนัง (`wall_clock`)
6. สมุดระบบไฟ (`maintenance_log`)
7. ความทรงจำกิเดียนอยู่ด้วยตอนไฟดับ (`gideon_blackout_alibi`)

คำสั่งที่ตัวทดสอบส่งคือ `infer claim_two_times` พร้อม `ParsedCommand.evidence` ทั้ง7รายการ หน้าเว็บส่งรายการที่เลือกในหน้าต่างข้อสรุปให้ API จัดเข้าคำสั่ง ไม่มีการรับรองจากการพิมพ์ชื่อข้อสรุปอย่างเดียว

เมื่อข้อสรุปผ่าน กล่าวหากิเดียนแล้วเลือก19รายการในช่อง `submitted_evidence` ของ walkthrough ประกอบด้วย7รายการข้างต้น และ12รายการต่อไปนี้:

```text
judicial_transfer_order
dossier_missing_file_c
burnt_folder_c
file_c_initials
gideon_no_early_alibi
staff_service_record
postponed_meeting_claim
staff_no_message
obsidian_cufflink
gideon_missing_button
wax_seal_imprint
gideon_signet_ring
```

ผลที่คาดหวังคือ `true_ending` และสี่เสาครบ บันทึกปีบนกระเป๋าเป็นคำใบ้เปิดด่าน ไม่ใช่หลักฐานที่ต้องยื่นในคดี ส่วนกุญแจเป็นของติดตัว ไม่ใช้โควตาหลักฐานยื่น

## 2. เปลี่ยนเป็นทางที่ใช้ชา

ระหว่างอยู่ตู้4ให้ตรวจ `second_teacup` ก่อน `tea_lozenge_trace` แล้วตรวจ `gideon_lozenge_tin` ที่ตู้5 ทั้งสามรายการเป็นสายชา

| คู่ | เปลี่ยนจากชุด19รายการอย่างไร | รวม |
|---|---|---:|
|ชา + กระดุม|เอา `wax_seal_imprint`, `gideon_signet_ring` ออก แล้วเพิ่มสายชาทั้ง3|20|
|ชา + ตรา|เอา `obsidian_cufflink`, `gideon_missing_button` ออก แล้วเพิ่มสายชาทั้ง3|20|

ทั้งสองคู่ยังใช้ข้อสรุปสองเวลาและหลักฐานฐานเดียวกัน รายการครบอยู่ใน `winning_cases.tea_button` และ `winning_cases.tea_wax` ฉากจบไม่ควรอธิบายเหมือนผู้เล่นได้ยื่นสายที่ตัดออกไปด้วย

## 3. เส้นทางเสริมที่เล่าแรงจูงใจคนอื่น

**ลิโอรา:** ที่ตู้4ถาม `interrogate dr_liora_venn examination` เพื่อรับ `medical_key` แล้วใช้ `unlock medical_room_door medical_key` ตรวจ `secret_file` กับ `liora_patient_log` กลับถาม `interrogate dr_liora_venn father` เพื่อฟังเหตุที่เก็บแฟ้มเอเลียส จากนั้นตู้3ถาม `interrogate patient_witness care` สมุดรักษาและพยานร่วมกับช่วงเหตุจึงหักล้างโอกาสของเธอ

**วินเซนต์:** ที่ตู้6ตรวจ `vincent_ticket`, `mara_job_note`, `vincent_blood`, `wire_cutters` ถาม `arrival` และ `job` กลับตู้3ถาม `car_attendant station` เพื่อยืนยันตัวตนที่เคาน์เตอร์ก่อนขึ้นรถ ใบรับรองกับตั๋วและช่วงเหตุจึงหักล้างโอกาสฆาตกรรม

หากต้องการเผชิญหลักฐานไฟดับ ให้เปิดห้องไฟแล้วตรวจ `power_panel`, `fuse_box`, `cut_copper_wire`, `tool_marks` เมื่อเทียบกับคีมได้จึงถาม `vincent_gray blackout` วินเซนต์ยอมรับการตัดสายและการเข้าไปพบร่าง สารภาพเรื่องไฟไม่ได้ทำหน้าที่หักล้างโอกาสฆาตกรรมก่อนขึ้นรถ

**คำโกหกกิเดียน:** หลังฟังพนักงานเรื่องข่าวเลื่อนนัด กลับถาม `gideon_hart message` หลังเชื่อมสำนวนให้ถาม `gideon_hart past` บทเหล่านี้ขยายความเข้าใจและปฏิกิริยาตัวละคร ไม่บังคับเป็นหลักฐานเพิ่มในชุดขั้นต่ำ

## 4. จุดตรวจความล้มเหลวที่ตั้งใจรองรับ

- ตรวจของภายในกระเป๋าก่อนเปิดรหัส: ไม่มอบหลักฐาน
- ตรวจประตูอย่างเดียว: ประตูยังล็อก
- พิมพ์หัวข้อ `impact` ก่อนพบนาฬิกาพก: ยังไม่เปิดบทนั้น
- กล่าวหาพนักงานหรือผู้ป่วย: ปฏิเสธ เพราะเป็นพยาน
- เสนอข้อสรุปถูกแต่แนบข้อมูลไม่ครบ: ยังไม่รับรอง และไม่ใช้โอกาสกล่าวหา
- เก็บหลักฐานครบแต่ไม่เสนอ `claim_two_times`: ไม่ได้ True Ending
- รู้หลักฐานที่อยู่ของวินเซนต์/ลิโอราครบแล้วแต่ละออกจากคำกล่าวหา: ยังคงปฏิเสธข้อกล่าวหาที่ขัดข้อมูลซึ่งรู้แล้ว
- เวลาเกิน90นาที: ปิดช่วงสอบสวนบนรถด้วย `cold_arrival`

นี่เป็นเส้นทางตรวจตรรกะและการเข้าถึงข้อมูล ไม่ใช่ผลยืนยันว่าผู้เล่นใหม่เข้าใจหรือเล่นจบภายในเวลาที่เหมาะสม โปรดใช้ [แผนทดลอง](research-protocol-2026-10-12.md) เมื่อตรวจประสบการณ์ผู้เล่น
