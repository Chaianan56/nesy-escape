# ⚙️ Nocturne Express 1938: Rules & Clues Specification

> **ข้อกำหนดหลักฐานและกฎการตัดสินของ Symbolic Rule Engine**

---

## 📌 หมวดหมู่หลักฐานและข้อเท็จจริง (Facts & Clues Taxonomy)

### หมวด A: ข้อเท็จจริงด้านเวลา (Temporal Facts)
* `FACT_WALL_CLOCK_STOPPED`: นาฬิกาไฟฟ้าบนผนังหยุดเดินที่เวลา 21:15 น. (เหยื่อล่อเชิงเวลาจากเหตุไฟดับ)
* `FACT_POCKET_WATCH_STOPPED`: นาฬิกาพกกลไกในอกเสื้อ Cassian หน้าปัดแตกหยุดเดินที่เวลา **20:25 น.** (เวลาตายจริง)
* `FACT_CONDUCTOR_LAST_VISIT`: พนักงานเสิร์ฟชาพบ Cassian ยังมีชีวิตอยู่เมื่อเวลา 20:10 น.
* `FACT_TUNNEL_WINDOW`: รถไฟวิ่งลอดผ่านอุโมงค์เหมืองถ่านหินแบล็กโฮลช่วงเวลา 20:20 – 20:26 น.
* `FACT_HALBERD_ARRIVAL`: รถไฟเทียบชานชาลาสถานีฮัลเบิร์ดเวลา 20:45 น. (Narin ก้าวขึ้นขบวน)
* `FACT_HEATER_SHUTDOWN`: ฮีตเตอร์ดับตอน 21:15 น. ทำให้อุณหภูมิห้องลดฮวบ

---

### หมวด B: ข้อเท็จจริงทางการแพทย์ (Forensic Facts)
* `FACT_AUTOPSY_LIVIDITY`: รอยตกตะกอนของเลือด (Lividity) บ่งชี้ว่าเหยื่อเสียชีวิตมาแล้วไม่ต่ำกว่า 1 ชั่วโมง (เสียชีวิตก่อน 20:30 น.)
* `FACT_AUTOPSY_COLD_BODY`: ร่างกายเหยื่อเริ่มเย็นชืดตั้งแต่ก่อนระบบฮีตเตอร์จะดับ
* `FACT_TESTIMONY_VINCENT_COLD`: คำให้การของ Vincent: *"ตอนย่องเข้าไปในความมืด ร่างกายของเขาก็เย็นเฉียบไปแล้ว"*

---

### หมวด C: วัตถุพยานในห้องเกิดเหตุ (Physical Clues in Room)
1. `CLUE_BURNT_FOLDER_C`: เศษเอกสารในถาดเขี่ยบุหรี่ถูกไฟไหม้บางส่วน ปรากฏข้อความอนุมัติงบปี 1923 พร้อมรหัส `[G.H.]` และหมึกสีน้ำเงินอมเขียว
2. `CLUE_WAX_SEAL_IMPRINT`: ก้อนขี้ผึ้งสีแดงใต้โต๊ะมีรอยบุบกระแทกเป็นลวดลายเรขาคณิตตรงกับหน้าตัดแหวนตรา
3. `CLUE_OBSIDIAN_CUFFLINK`: กระดุมข้อมือเงินฝังหินออบซิเดียน 1 เม็ด ตกอยู่ใต้ร่างของ Cassian
4. `CLUE_SECOND_TEACUP`: มีถ้วยชาใบที่ 2 บนโต๊ะ พบคราบยาอมกลิ่นการบูร-สะระแหน่ตกค้าง
5. `CLUE_RED_SOOT_ROOM`: ละอองเขม่าซัลเฟอร์สีแดงจากอุโมงค์แบล็กโฮลปลิวเข้ามาเกาะบนกองเลือดและพื้นห้อง

---

### หมวด D: ร่องรอยบนตัวผู้ต้องสงสัย (Suspect Physical Traces)
* `CLUE_GIDEON_SUIT_CUFF`: ปลายแขนเสื้อสูทข้างซ้ายของ Gideon มีรอยด้ายขาดและกระดุมออบซิเดียนหลุดหายไป 1 เม็ด
* `CLUE_GIDEON_SIGNET_RING`: Gideon สวมแหวนตราประจำตระกูลที่นิ้วก้อยขวา ลวดลายตรงกับรอยประทับบนขี้ผึ้ง
* `CLUE_GIDEON_PASTILLE_BOX`: Gideon พกตลับยาอมโลหะ บรรจุยาอมการบูร-สะระแหน่ชนิดเดียวกับที่พบในถ้วยชาใบที่ 2
* `CLUE_GIDEON_RED_SOOT`: รอยพับปลายแขนเสื้อสูทของ Gideon มีละอองเขม่าถ่านหินซัลเฟอร์สีแดงชนิดเดียวกับในอุโมงค์และห้องผู้ตาย
* `CLUE_VINCENT_BLOOD_CUFF`: ปลายแขนเสื้อ Vincent มีคราบเลือดสดของ Cassian
* `CLUE_VINCENT_TOOLS`: Vincent พกคีมตัดสายไฟด้ามยางและเศษลวดทองแดง

---

### หมวด E: ข้ออ้างที่อยู่และพยานบุคคล (Alibi & Testimonies)
* `ALIBI_GIDEON_BLACKOUT`: Gideon ยืนคุยและจุดไฟแช็กกับ Narin ในตู้ 5 ตลอดช่วง 21:15 – 21:18 น.
* `ALIBI_GIDEON_PRE_HALBERD`: Gideon อ้างว่าอ่านหนังสือคนเดียวในห้องพักช่วง 20:00 – 20:40 น. (ไม่มีพยาน)
* `TESTIMONY_VINCENT_PURPOSE`: Vincent ให้การว่ารับจ้าง Mara Voss มาเพื่อขโมยกระเป๋าคืน ไม่ได้ตั้งใจฆ่าคน
* `TESTIMONY_LIORA_FEAR`: Liora มีพิรุธเพราะกลัวว่าจะถูกเครือข่ายอำนาจมืดสั่งฆ่าปิดปากเป็นรายต่อไป

---

## 🎯 กฎการตรวจสอบหลักฐานยืดหยุ่น (Flexible Evidence Threshold Rule)

ในการกล่าวหา **Gideon Hart** เพื่อปลดล็อก **True Ending**:
* **เงื่อนไขที่ 1 (Break False Timeline)**: ต้องพิสูจน์ได้ว่าเวลาตายจริงคือช่วง **20:20 – 20:25 น.** (หักล้าง Alibi ช่วง 21:15 น.)
* **เงื่อนไขที่ 2 (Flexible Physical Evidence Threshold)**: ต้องถือหลักฐานกายภาพมัดตัว Gideon **อย่างน้อย 3 ใน 5 ชิ้น**:

$$\text{Evidence Count} = \sum_{i=1}^{5} \mathbb{I}(\text{Clue}_i \in \text{PlayerInventory}) \ge 3$$

รายการหลักฐานกายภาพ 5 ชิ้น:
1. `CLUE_BURNT_FOLDER_C`
2. `CLUE_WAX_SEAL_IMPRINT` (หรือ `CLUE_GIDEON_SIGNET_RING`)
3. `CLUE_OBSIDIAN_CUFFLINK` (หรือ `CLUE_GIDEON_SUIT_CUFF`)
4. `CLUE_SECOND_TEACUP` (หรือ `CLUE_GIDEON_PASTILLE_BOX`)
5. `CLUE_RED_SOOT_ROOM` (หรือ `CLUE_GIDEON_RED_SOOT`)

> [!TIP]
> หากสะสมหลักฐานกายภาพได้ **น้อยกว่า 3 ชิ้น** แต่เลือกกล่าวหา Gideon ระบบจะส่งผลลัพธ์เป็น **Tragic Ending: อำนาจเหนือกฎหมาย**
