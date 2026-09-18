# SleepSense AI — ระบบ AI ตรวจคัดกรองภาวะหยุดหายใจขณะหลับจากไฟล์เสียง

โปรเจกต์ต้นแบบที่ใช้โมเดล AI (CNN) วิเคราะห์ไฟล์เสียงขณะนอนหลับ เพื่อคัดกรองเบื้องต้นว่ามีแนวโน้มเป็นภาวะหยุดหายใจขณะหลับ (Sleep Apnea) หรือไม่ พัฒนาโดยใช้ชุดข้อมูล [APSAA (Audio-Polygraphy Dataset for Sleep Apnea Analysis)](README.txt)

**ข้อจำกัดสำคัญ:** นี่คือโปรเจกต์ต้นแบบเพื่อการศึกษา ความแม่นยำของโมเดลอยู่ที่ประมาณ 76% accuracy / 64% F1-score **ไม่ใช่เครื่องมือวินิจฉัยทางการแพทย์**

## โครงสร้างโปรเจกต์

```
APSAA/
├── 20210919A/ ... 20220211B/   # ข้อมูลดิบ (เสียง + polygraph + annotation) 32 คน
├── scripts/                     # ขั้นตอนที่ 1-2: เตรียมข้อมูลและเทรนโมเดล
│   ├── prepare_dataset.py       # ตัดเสียงเป็นช่วง 10 วิ + ติด label จาก annotation
│   ├── audio_dataset.py         # PyTorch Dataset: เสียง -> log-mel spectrogram
│   ├── model.py                 # สถาปัตยกรรม CNN (ApneaCNN)
│   ├── train.py                 # เทรนโมเดล
│   └── quick_eval.py            # ประเมินผลโมเดลแบบเร็วบนชุด validation
├── prepared_dataset/            # ผลลัพธ์จาก prepare_dataset.py + checkpoint โมเดล
│   ├── manifest_full.csv / manifest_train.csv / manifest_val.csv
│   └── best_model.pt            # น้ำหนักโมเดลที่ดีที่สุด (ใช้จริงใน backend)
├── backend/                      # ขั้นตอนที่ 3: FastAPI server
│   ├── inference.py              # โหลดโมเดล + วิเคราะห์ไฟล์เสียงเต็มไฟล์
│   └── main.py                   # API endpoints (/health, /analyze) + เสิร์ฟหน้าเว็บ
├── frontend/                     # ขั้นตอนที่ 4: หน้าเว็บ
│   ├── index.html / style.css / app.js
├── requirements.txt
└── PROJECT_README.md             # ไฟล์นี้
```

## วิธีติดตั้งและรัน

```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --port 8000
```

จากนั้นเปิดเบราว์เซอร์ไปที่ `http://localhost:8000`

## Pipeline โดยสรุป

1. **เตรียมข้อมูล** (`scripts/prepare_dataset.py`) — ตัดเสียงแต่ละคนเป็นช่วงละ 10 วินาที ติด label ว่า "apnea" หรือ "ปกติ" จากการเทียบกับเวลาที่มี annotation (Obstructive/Central/Mixed Apnea, Hypopnea) แบ่ง train/validation ตามรายคน
2. **เทรนโมเดล** (`scripts/train.py`) — แปลงเสียงเป็น log-mel spectrogram แล้วเทรน CNN จำแนก 2 กลุ่ม บันทึก checkpoint ที่ F1 ดีที่สุดไว้ที่ `prepared_dataset/best_model.pt`
3. **Backend** (`backend/`) — โหลด checkpoint มาให้บริการผ่าน REST API รับไฟล์เสียงเต็มไฟล์ ตัดเป็นช่วง 10 วิเหมือนตอนเทรน รันโมเดลทีละช่วง รวมช่วงต่อเนื่อง (≥20 วิ) เป็น "เหตุการณ์"
4. **Frontend** (`frontend/`) — หน้าเว็บอัปโหลดไฟล์เสียง แสดงกราฟความเสี่ยงตลอดคืน, สรุปสถิติ, และตารางเหตุการณ์

## ผลการทดสอบโมเดล (ล่าสุด)

| ตัวชี้วัด | ค่า |
|---|---|
| Accuracy | ~76% |
| Precision | ~57% |
| Recall | ~74% |
| F1-score | ~64% |

ประเมินบนชุด validation (6 คน, แยกจากชุดฝึกทั้งหมด)

## ข้อจำกัดที่ทราบแล้ว

- โมเดลจำแนกทีละช่วง 10 วินาทีแบบแยกขาดจากกัน ไม่มีบริบทเวลาต่อเนื่อง อาจทายผิดจากเสียงรบกวน/เสียงกรนดังต่อเนื่อง
- Precision ต่ำกว่า Recall — มีแนวโน้ม over-predict (ทายว่าเป็น apnea เกินจริง) โดยเฉพาะกับคนที่มีอาการหนักอยู่แล้ว
- เทรนจากข้อมูลแค่ 26 คน ยังไม่หลากหลายพอที่จะครอบคลุมทุกกรณีจริง
- รองรับไฟล์ `.wav` และ `.flac` เท่านั้น

## แนวทางพัฒนาต่อ

- เพิ่มบริบทเวลาให้โมเดล (เช่น RNN/LSTM ต่อจาก CNN)
- Data augmentation เพื่อเพิ่มความหลากหลายของข้อมูลเทรน
- ทดสอบและปรับ decision threshold ให้เหมาะสมยิ่งขึ้น
