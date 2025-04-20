const express = require('express');
const mysql = require('mysql2');
const bodyParser = require('body-parser');
const path = require('path');
const cors = require('cors');

const app = express();
const port = 3000;

// إعداد الاتصال بقاعدة البيانات MySQL
const db = mysql.createConnection({
    host: 'localhost',
    user: 'root',
    password: '1234', // اضبط هذا حسب إعداداتك
    database: 'pharmacy_db'
});

// التحقق من الاتصال بقاعدة البيانات
db.connect(err => {
    if (err) {
        console.error('خطأ في الاتصال بقاعدة البيانات:', err);
        return;
    }
    console.log('تم الاتصال بقاعدة البيانات بنجاح');
});

// تفعيل CORS ومعالجة JSON
app.use(cors());
app.use(bodyParser.json());

// تقديم الملفات الثابتة من مجلد public
app.use(express.static(path.join(__dirname, 'public')));

/**
 * GET /medications: إرجاع جميع الأدوية (مثال)
 */
app.get('/medications', (req, res) => {
    const query = `
        SELECT m.medication_id, m.name, m.generic_name, m.\`class\`, m.indication, 
               m.frequency, m.max_dose, m.contraindications, m.drug_interactions, 
               m.pregnancy_safety, m.side_effects, m.high_risk, m.hazard, t.type_name
        FROM medications m
        JOIN medication_types t ON m.type_id = t.type_id;
    `;
    db.query(query, (err, results) => {
        if (err) {
            console.error('خطأ في جلب البيانات:', err);
            return res.status(500).send('خطأ في الخادم');
        }
        res.json(results);
    });
});

/**
 * POST /medications: إضافة دواء جديد (مثال)
 */
app.post('/medications', (req, res) => {
    const {
        type_id,
        name,
        generic_name,
        class: medClass,
        indication,
        frequency,
        max_dose,
        contraindications,
        drug_interactions,
        pregnancy_safety,
        side_effects,
        high_risk,
        hazard
    } = req.body;

    const query = `
        INSERT INTO medications (
            type_id, name, generic_name, \`class\`, indication, frequency, 
            max_dose, contraindications, drug_interactions, pregnancy_safety, 
            side_effects, high_risk, hazard
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    `;
    const values = [
        type_id, name, generic_name, medClass, indication, frequency, 
        max_dose, contraindications, drug_interactions, pregnancy_safety, 
        side_effects, high_risk || false, hazard || false
    ];

    db.query(query, values, (err, results) => {
        if (err) {
            console.error('خطأ في إضافة الدواء:', err);
            return res.status(500).send('خطأ في الخادم');
        }
        res.status(201).send('تمت إضافة الدواء بنجاح');
    });
});

/**
 * POST /get-medication: البحث عن دواء وإرجاع بياناته
 * يتم استخدام النص المرسل في req.body.query للبحث.
 * إذا حدث خطأ يتم إرجاع رسالة عامة دون تفاصيل.
 */
app.post('/get-medication', (req, res) => {
    const { query } = req.body;
    if (!query) {
        return res.status(400).json({ error: 'لم يتم إرسال حقل query في الطلب' });
    }
    const sql = `
        SELECT 
            type_id, 
            name, 
            generic_name,
            \`class\`,
            indication,
            frequency,
            max_dose,
            contraindications,
            drug_interactions,
            pregnancy_safety,
            side_effects,
            high_risk,
            hazard
        FROM medications
        WHERE name LIKE ? OR generic_name LIKE ?
        LIMIT 1
    `;
    db.query(sql, [`%${query}%`, `%${query}%`], (err, results) => {
        if (err) {
            console.error('خطأ في الاستعلام:', err);
            return res.status(500).json({ error: 'حدث خطأ أثناء معالجة الطلب.' });
        }
        if (!results || results.length === 0) {
            return res.json({}); 
        }
        const row = results[0];
        res.json({
            type_id: row.type_id,
            name: row.name,
            generic_name: row.generic_name,
            class: row.class,
            indication: row.indication,
            frequency: row.frequency,
            max_dose: row.max_dose,
            contraindications: row.contraindications,
            drug_interactions: row.drug_interactions,
            pregnancy_safety: row.pregnancy_safety,
            side_effects: row.side_effects,
            high_risk: row.high_risk,
            hazard: row.hazard
        });
    });
});

// إعادة ملف index.html عند طلب الجذر "/"
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// تشغيل الخادم
app.listen(port, () => {
    console.log(`الخادم يعمل على http://localhost:${port}`);
});
